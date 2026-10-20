#pragma once

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <time.h>

// Linux CLOCK_MONOTONIC is shared by all Pi processes. The browser reports
// local durations only; its clock must never be subtracted from this one.
namespace bridge_perf {
inline int port(const char* key, int fallback) {
    const char* text = std::getenv(key);
    if (!text || !*text) return fallback;
    char* end = nullptr;
    const long value = std::strtol(text, &end, 10);
    return end && !*end && value >= 1024 && value <= 65535 ? static_cast<int>(value) : fallback;
}
inline long long nowNS() {
    timespec ts{};
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return static_cast<long long>(ts.tv_sec) * 1000000000LL + ts.tv_nsec;
}
inline FILE* output(const char* role) {
    static FILE* publisher = nullptr;
    static FILE* controller = nullptr;
    FILE*& file = std::string(role) == "controller" ? controller : publisher;
    if (file) return file;
    const char* directory = std::getenv("STARCOASTER_PERF_DIR");
    if (!directory || !*directory) return nullptr;
    const std::string path = std::string(directory) + "/openbw-" + role + "-events.jsonl";
    file = std::fopen(path.c_str(), "a");
    if (file) std::setvbuf(file, nullptr, _IOLBF, 0);
    return file;
}
inline void snapshot(const char* role, unsigned long long seq, int frame, int total, int omitted, int attacking,
                     size_t bytes, long long buildUS, long long serializeUS,
                     long long writeUS, size_t queued) {
    FILE* file = output(role);
    if (!file) return;
    std::fprintf(file, "{\"source\":\"openbw-%s\",\"stage\":\"snapshot_publish\","
        "\"mono_ns\":%lld,\"seq\":%llu,\"bw_tick\":%d,\"unit_total\":%d,"
        "\"unit_omitted\":%d,\"unit_attacking\":%d,\"bytes\":%zu,\"build_us\":%lld,\"serialize_us\":%lld,"
        "\"write_us\":%lld,\"queued_bytes\":%zu}\n",
        role, nowNS(), seq, frame, total, omitted, attacking, bytes, buildUS, serializeUS, writeUS, queued);
}
inline void frame(const char* role, int frame, int count, long long elapsedNS,
                  long long workUS, long long maxWorkUS, long long sleepUS, int overruns,
                  long long maxDelayUS, long long p50WorkUS, long long p95WorkUS,
                  long long p99WorkUS) {
    FILE* file = output(role);
    if (!file) return;
    std::fprintf(file, "{\"source\":\"openbw-%s\",\"stage\":\"frame_summary\","
        "\"mono_ns\":%lld,\"bw_tick\":%d,\"frames\":%d,\"elapsed_ns\":%lld,"
        "\"work_us\":%lld,\"max_work_us\":%lld,\"sleep_us\":%lld,"
        "\"overruns\":%d,\"max_delay_us\":%lld,\"work_p50_us\":%lld,"
        "\"work_p95_us\":%lld,\"work_p99_us\":%lld}\n",
        role, nowNS(), frame, count, elapsedNS, workUS, maxWorkUS, sleepUS, overruns,
        maxDelayUS, p50WorkUS, p95WorkUS, p99WorkUS);
}
inline void command(const char* role, const std::string& id, int frame, bool accepted, long long durationUS) {
    FILE* file = output(role);
    if (!file) return;
    // Existing command IDs are restricted to session and decimal serials.
    std::fprintf(file, "{\"source\":\"openbw-%s\",\"stage\":\"command_execute\","
        "\"mono_ns\":%lld,\"command_id\":\"%s\",\"bw_tick\":%d,"
        "\"accepted\":%s,\"duration_us\":%lld}\n",
        role, nowNS(), id.c_str(), frame, accepted ? "true" : "false", durationUS);
}
} // namespace bridge_perf
