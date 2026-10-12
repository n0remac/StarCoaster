#pragma once

#include <BWAPI.h>
#include <nlohmann/json.hpp>

#include <arpa/inet.h>
#include <fcntl.h>
#include <sys/socket.h>
#include <unistd.h>

#include <algorithm>
#include <cmath>
#include <cerrno>
#include <cstring>
#include <iostream>
#include <map>
#include <set>
#include <string>
#include <vector>

// All network input is parsed and applied by onFrame on the BWAPI simulation
// thread. The socket callback never touches game state.
class WorldAdapter {
    using json = nlohmann::json;
    struct Target { std::string id; BWAPI::Unit unit = nullptr; int proxyID = -1; int lastHP = 0; bool reported = false; bool confirmed = false; };
    struct PendingTarget { std::string id; int x = 0; int y = 0; int health = 0; bool reused = false; };
public:
    ~WorldAdapter() { if (socket_ >= 0) ::close(socket_); }
    void onFrame(BWAPI::Game* game) {
        if (socket_ < 0) connect(game);
        if (socket_ < 0) return;
        char data[8192];
        for (;;) {
            const ssize_t n = ::recv(socket_, data, sizeof(data), 0);
            if (n > 0) { incoming_.append(data, static_cast<size_t>(n)); if (incoming_.size() > 8388608) { disconnect(); return; } }
            else if (n == 0) { disconnect(); return; }
            else if (errno == EAGAIN || errno == EWOULDBLOCK) break;
            else { disconnect(); return; }
        }
        size_t newline;
        while ((newline = incoming_.find('\n')) != std::string::npos) {
            const auto line = incoming_.substr(0,newline); incoming_.erase(0,newline+1);
            if (line.size() > 1048576) { disconnect(); return; }
            try { handle(game,json::parse(line)); } catch (const std::exception& e) { std::cerr << "[world] invalid message: " << e.what() << std::endl; }
        }
        flush();
        if (initializing_) resolveTargets(game);
        if (!ready_) return;
        const int frame = game->getFrameCount();
        for (auto& [id,target] : targets_) {
            const int hp = target.unit && target.unit->exists() ? target.unit->getHitPoints() : 0;
            if (hp != target.lastHP) { target.lastHP=hp; send("entity.state",{{"id",id},{"proxy_id","openbw:"+std::to_string(target.proxyID)},{"health",hp}},revision_,frame); }
            if (hp==0 && !target.reported) {
                target.reported=true;
                send("combat.event",{{"id",session_+":"+std::to_string(frame)+":destruction:"+std::to_string(++event_)},
                    {"entity_id",id},{"proxy_id","openbw:"+std::to_string(target.proxyID)},
                    {"type","destruction"},{"health",0}},revision_,frame);
                std::cerr << "[world] target destroyed id=" << id << " frame=" << frame << std::endl;
            }
        }
        // A generic smoke combat loop uses native BWAPI orders and damage. It
        // runs only when a hostile Zergling already exists on the base map.
        if (frame%24==0) {
            for (auto unit : game->getAllUnits()) {
                if (!unit || !unit->exists() || unit->getPlayer()!=game->self()
                    || unit->getType()!=BWAPI::UnitTypes::Zerg_Zergling) continue;
                auto current=std::find_if(targets_.begin(),targets_.end(),[](const auto& item) {
                    return item.second.unit && item.second.unit->exists();
                });
                if (current!=targets_.end()) unit->attack(current->second.unit);
            }
        }
        if (frame%3==0) publishActors(game,frame);
    }
private:
    void connect(BWAPI::Game* game) {
        const int fd=::socket(AF_INET,SOCK_STREAM,0); if (fd<0) return;
        sockaddr_in address{}; address.sin_family=AF_INET; address.sin_port=htons(40011); address.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
        if (::connect(fd,reinterpret_cast<sockaddr*>(&address),sizeof(address))!=0) { ::close(fd); return; }
        ::fcntl(fd,F_SETFL,::fcntl(fd,F_GETFL,0)|O_NONBLOCK); socket_=fd;
        send("world.hello",{{"capabilities",{"snapshot","combat.event","navigation.obstacle.remove"}},
            {"map_width",game->mapWidth()},{"map_height",game->mapHeight()}},1,0);
        std::cerr << "[world] connected to bridge service" << std::endl;
    }
    void disconnect() { if (socket_>=0) ::close(socket_); socket_=-1; incoming_.clear(); outgoing_.clear(); ready_=false; initializing_=false; pending_.clear(); targets_.clear(); }
    void flush() {
        while (socket_>=0 && !outgoing_.empty()) {
            const ssize_t n=::send(socket_,outgoing_.data(),outgoing_.size(),MSG_NOSIGNAL);
            if (n>0) outgoing_.erase(0,static_cast<size_t>(n));
            else if (n<0 && (errno==EAGAIN || errno==EWOULDBLOCK)) return;
            else { disconnect(); return; }
        }
    }
    void send(const std::string& kind,const json& payload,uint64_t revision,int frame) {
        const json message={{"v",1},{"kind",kind},{"session",session_.empty()?"openbw-startup":session_},
            {"op_id","openbw:"+std::to_string(++sequence_)},{"source","openbw"},
            {"revision",revision},{"bw_tick",frame},{"payload",payload}};
        outgoing_+=message.dump()+"\n"; flush();
    }
    void ack(const json& message,bool accepted,const std::string& error="") {
        send("world.ack",{{"op_id",message.at("op_id")},{"accepted",accepted},{"error",error}},
             message.at("revision").get<uint64_t>(),0);
    }
    void handle(BWAPI::Game* game,const json& message) {
        if (message.value("v",0)!=1 || !message.contains("payload") || !message.contains("op_id")) return;
        const std::string kind=message.value("kind","");
        const auto& payload=message.at("payload");
        if (kind=="world.ack") return;
        if (kind=="world.snapshot.begin") {
            const int width=payload.at("width"), height=payload.at("height"), chunks=payload.at("chunks");
            if (width<1 || height<1 || width>1024 || height>1024 || chunks<1 || chunks>100000) { ack(message,false,"invalid_dimensions"); return; }
            session_=message.at("session").get<std::string>(); revision_=message.at("revision").get<uint64_t>();
            expectedChunks_=chunks; receivedChunks_=0; width_=width; height_=height; entities_.clear(); terrain_.clear(); targets_.clear(); obstacles_.clear(); chunkOps_.clear(); ready_=false;
            ack(message,true); return;
        }
        if (message.value("session","")!=session_ || message.at("revision").get<uint64_t>()<revision_) { ack(message,false,"stale_session"); return; }
        if (kind=="world.snapshot.chunk") {
            const auto opID=message.at("op_id").get<std::string>();
            if (chunkOps_.count(opID)) { ack(message,true); return; }
            if (receivedChunks_>=expectedChunks_ || payload.value("index",-1)!=receivedChunks_) { ack(message,false,"unexpected_chunk"); return; }
            for (const auto& e : payload.value("entities",json::array())) {
                const auto id=e.at("id").get<std::string>(); if (entities_.count(id)) { ack(message,false,"duplicate_entity"); return; }
                entities_[id]=e;
            }
            for (const auto& cell : payload.value("terrain",json::array())) terrain_.push_back(cell);
            ++receivedChunks_; chunkOps_.insert(opID); ack(message,true); return;
        }
        if (kind=="world.snapshot.end") {
            if (receivedChunks_!=expectedChunks_ || payload.value("entities",-1)!=static_cast<int>(entities_.size())
                || payload.value("terrain",-1)!=static_cast<int>(terrain_.size())) { ack(message,false,"incomplete_snapshot"); return; }
            for (const auto& [id,e]:entities_) {
                if (e.at("collision").value("blocks",false)) {
                    const auto rects=e.at("geometry").value("rects",json::array());
                    if (!rects.empty()) obstacles_[id]=rects;
                }
            }
            requestTargets(game); ack(message,true); return;
        }
        if (kind=="combat.result") {
            const auto id=payload.value("entity_id",""); if (targets_.count(id)) targets_[id].confirmed=payload.value("state","")=="removal_confirmed";
            revision_=std::max(revision_,message.at("revision").get<uint64_t>());
            ack(message,true); return;
        }
        if (kind=="navigation.obstacle.remove") {
            const auto id=payload.value("id","");
            if (!entities_.count(id)) { ack(message,false,"unknown_entity"); return; }
            obstacles_.erase(id);
            revision_=std::max(revision_,message.at("revision").get<uint64_t>());
            ack(message,true); return;
        }
        if (kind=="entity.upsert" || kind=="entity.remove" || kind=="entity.transform" || kind=="entity.state"
            || kind=="navigation.obstacle.upsert" || kind=="navigation.terrain.update") {
            // The contract is understood, but runtime insertion and region
            // rebuilding are deliberately unavailable in world.v1 startup mode.
            ack(message,false,"live_update_unsupported"); return;
        }
        ack(message,false,"unsupported_operation");
    }
    void requestTargets(BWAPI::Game* game) {
        unsupported_=json::array(); unsupportedTotal_=0; unsupportedReasons_=json::object(); pending_.clear(); usedUnits_.clear();
        auto self=game->self(); auto enemy=game->enemy();
        if (!enemy) for (auto player : game->getPlayers()) if (player && player!=self && player->getType().toString()=="Player") { enemy=player; break; }
        if (self && enemy && !self->isEnemy(enemy)) game->setAlliance(enemy,false,false);
        for (const auto& [id,e] : entities_) {
            if (!e.value("destructible",false)) continue;
            if (!e.at("combat").value("targetable",false)) { reportUnsupported(id,"not_targetable"); continue; }
            if (!enemy) { reportUnsupported(id,"no_enemy_player"); continue; }
            const auto& geometry=e.at("geometry"); const auto rects=geometry.value("rects",json::array());
            if (rects.empty()) { reportUnsupported(id,"empty_footprint"); continue; }
            int minX=1<<30,minY=1<<30,maxX=0,maxY=0;
            for (const auto& rect:rects) { const int x=rect.at("x"),y=rect.at("y"),w=rect.at("width"),h=rect.at("height"); minX=std::min(minX,x); minY=std::min(minY,y); maxX=std::max(maxX,x+w); maxY=std::max(maxY,y+h); }
            const int x=(minX+maxX)/2,y=(minY+maxY)/2;
            if (x<0 || y<0 || x>=game->mapWidth()*32 || y>=game->mapHeight()*32) { reportUnsupported(id,"outside_base_map"); continue; }
            if (pending_.size()>=128) { reportUnsupported(id,"target_capacity"); continue; }
            bool alreadyPresent=false;
            for (auto unit:game->getAllUnits()) {
                if (!unit || !unit->exists() || unit->getPlayer()!=enemy || unit->getType()!=BWAPI::UnitTypes::Terran_Civilian) continue;
                const auto p=unit->getPosition();
                if (std::abs(p.x-x)<=16 && std::abs(p.y-y)<=16) { alreadyPresent=true; break; }
            }
            if (!alreadyPresent) game->createUnit(enemy,BWAPI::UnitTypes::Terran_Civilian,{x,y});
            // Multiplayer createUnit returns null even for an accepted command.
            // Identify the spawned engine unit on a later frame instead.
            pending_.push_back({id,x,y,e.at("combat").value("health",40),alreadyPresent});
        }
        initializing_=true; requestedFrame_=game->getFrameCount();
        std::cerr << "[world] requested targets=" << pending_.size() << " unsupported=" << unsupportedTotal_ << std::endl;
    }
    void resolveTargets(BWAPI::Game* game) {
        auto enemy=game->enemy();
        if (!enemy) for (auto player : game->getPlayers()) if (player && player!=game->self() && player->getType().toString()=="Player") { enemy=player; break; }
        for (auto it=pending_.begin();it!=pending_.end();) {
            BWAPI::Unit found=nullptr;
            for (auto unit:game->getAllUnits()) {
                if (!unit || !unit->exists() || unit->getPlayer()!=enemy || unit->getType()!=BWAPI::UnitTypes::Terran_Civilian || usedUnits_.count(unit->getID())) continue;
                const auto p=unit->getPosition(); if (std::abs(p.x-it->x)<=16 && std::abs(p.y-it->y)<=16) { found=unit; break; }
            }
            if (found) {
                if (!it->reused && it->health>0 && it->health<=100000) found->setHitPoints(it->health);
                usedUnits_.insert(found->getID()); targets_[it->id]={it->id,found,found->getID(),found->getHitPoints(),false,false};
                send("entity.state",{{"id",it->id},{"proxy_id","openbw:"+std::to_string(found->getID())},{"health",found->getHitPoints()}},revision_,game->getFrameCount());
                std::cerr << "[world] target id=" << it->id << " proxy=" << found->getID() << std::endl;
                it=pending_.erase(it);
            } else ++it;
        }
        if (!pending_.empty() && game->getFrameCount()-requestedFrame_<12) return;
        for (const auto& target:pending_) reportUnsupported(target.id,"proxy_not_created");
        pending_.clear(); initializing_=false; ready_=true;
        send("world.ready",{{"entities",entities_.size()},{"targets",targets_.size()},
            {"obstacles",obstacles_.size()},{"navigation","metadata_only"},
            {"unsupported",unsupported_},{"unsupported_total",unsupportedTotal_},
            {"unsupported_reasons",unsupportedReasons_}},revision_,game->getFrameCount());
        std::cerr << "[world] ready targets=" << targets_.size() << " unsupported=" << unsupportedTotal_ << std::endl;
    }
    void reportUnsupported(const std::string& id,const std::string& reason) {
        ++unsupportedTotal_;
        unsupportedReasons_[reason]=unsupportedReasons_.value(reason,0)+1;
        if (unsupported_.size()<256) unsupported_.push_back(id+":"+reason);
    }
    void publishActors(BWAPI::Game* game,int frame) {
        json units=json::array();
        for (auto unit:game->getAllUnits()) {
            if (!unit || !unit->exists()) continue;
            const auto type=unit->getType();
            if (type!=BWAPI::UnitTypes::Zerg_Zergling && type!=BWAPI::UnitTypes::Terran_Marine) continue;
            if (units.size()>=32) break;
            const auto position=unit->getPosition();
            const double turns=std::fmod(unit->getAngle()/(2.0*3.14159265358979323846)+1.0,1.0);
            const int facing=static_cast<int>(std::lround(turns*256.0))&255;
            const int hp=std::max(0,unit->getHitPoints());
            units.push_back({{"id","openbw:"+std::to_string(unit->getID())},
                {"kind",type==BWAPI::UnitTypes::Zerg_Zergling?"zerg_zergling":"terran_marine"},
                {"owner",unit->getPlayer()?unit->getPlayer()->getID():0},
                {"x",position.x},{"y",position.y},{"facing",facing},
                {"motion",unit->isMoving()?"walk":"idle"},
                {"hp",hp},{"max_hp",type.maxHitPoints()},{"attack_frames",0}});
        }
        send("combat.snapshot",{{"seq",++snapshotSequence_},{"bw_tick",frame},{"units",units}},revision_,frame);
    }
    int socket_=-1,expectedChunks_=0,receivedChunks_=0,width_=0,height_=0;
    bool ready_=false,initializing_=false; int requestedFrame_=0; uint64_t revision_=1,sequence_=0,event_=0,snapshotSequence_=0;
    std::string incoming_,outgoing_,session_;
    std::map<std::string,json> entities_; std::vector<json> terrain_; std::map<std::string,Target> targets_;
    std::map<std::string,json> obstacles_;
    std::vector<PendingTarget> pending_; std::set<int> usedUnits_; std::set<std::string> chunkOps_; json unsupported_=json::array();
    int unsupportedTotal_=0; json unsupportedReasons_=json::object();
};
