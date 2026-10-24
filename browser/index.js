/* StarCoaster adaptation of OpenRCT2's pinned emscripten/static/index.js.
 * The same OPENRCT2_WEB factory, IDBFS layout, and asset ZIP are used here.
 */
(async () => {
    const status = document.getElementById("status");
    const message = document.getElementById("message");
    const canvas = document.getElementById("canvas");
    const setStatus = (value) => { message.textContent = value; };
    const fail = (error) => {
        console.error("StarCoaster startup failed:", error);
        if (!status.isConnected) document.body.appendChild(status);
        status.classList.add("error");
        setStatus(`StarCoaster startup failed: ${error.message || error}`);
    };
    window.addEventListener("error", (event) => fail(event.error || event.message));
    window.addEventListener("unhandledrejection", (event) => fail(event.reason));
    const ensureDir = (fs, path) => {
        try { fs.mkdir(path); } catch (error) {
            if (!fs.isDir(fs.stat(path).mode)) throw error;
        }
    };
    const sync = (fs, populate) => new Promise((resolve, reject) =>
        fs.syncfs(populate, (error) => error ? reject(error) : resolve()));
    const clearDirectory = (fs, path) => {
        for (const name of fs.readdir(path)) {
            if (name === "." || name === "..") continue;
            const child = `${path}/${name}`;
            if (fs.isDir(fs.stat(child).mode)) {
                clearDirectory(fs, child);
                fs.rmdir(child);
            } else {
                fs.unlink(child);
            }
        }
    };
    const hash = async (data) => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", data)))
        .map((byte) => byte.toString(16).padStart(2, "0")).join("");
    const fetchRequired = async (path) => {
        const response = await fetch(path, { cache: "no-store" });
        if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
        return response;
    };
    const extract = async (fs, zip, base) => {
        for (const [name, entry] of Object.entries(zip.files)) {
            if (name.startsWith("/") || name.split("/").includes(".."))
                throw new Error(`Unsafe asset path: ${name}`);
            const target = `${base}${name}`;
            if (entry.dir) {
                ensureDir(fs, target.replace(/\/$/, ""));
                continue;
            }
            const parent = target.substring(0, target.lastIndexOf("/"));
            for (let end = base.length; end < parent.length; end++) {
                if (parent[end] === "/") ensureDir(fs, parent.substring(0, end));
            }
            ensureDir(fs, parent);
            fs.writeFile(target, await entry.async("uint8array"));
        }
    };
    const importDirectory = async (fs, handle, base, progress) => {
        for await (const entry of handle.values()) {
            if (entry.name === "." || entry.name === ".." || entry.name.includes("/"))
                throw new Error(`Unsafe RCT2 filename: ${entry.name}`);
            const target = `${base}/${entry.name}`;
            if (entry.kind === "directory") {
                ensureDir(fs, target);
                await importDirectory(fs, entry, target, progress);
            } else {
                const file = await entry.getFile();
                fs.writeFile(target, new Uint8Array(await file.arrayBuffer()));
                progress.count++;
                if (progress.count % 100 === 0)
                    setStatus(`Importing your RCT2 files… ${progress.count} files copied`);
            }
        }
    };
    const privateRct2Manifest = async () => {
        const response = await fetch("/private/rct2/manifest.json", { cache: "no-store" });
        if (response.status === 404) return null;
        if (!response.ok) throw new Error(`Private RCT2 provisioning: HTTP ${response.status}`);
        const manifest = await response.json();
        const digest = /^[0-9a-f]{64}$/;
        if (manifest.schema !== 1 || !digest.test(manifest.version) ||
            !Array.isArray(manifest.files) || !manifest.files.length ||
            !manifest.files.some((file) => file.path === "Data/ch.dat") ||
            manifest.files.some((file) => typeof file.path !== "string" ||
                file.path.includes("\\") || file.path.includes("\0") ||
                file.path.split("/").some((part) => !part || part === "." || part === "..") ||
                !Number.isSafeInteger(file.size) || file.size < 0 || !digest.test(file.sha256)))
            throw new Error("Private RCT2 asset manifest is invalid.");
        return manifest;
    };
    const provisionPrivateRct2 = async (fs, manifest) => {
        const totalBytes = manifest.files.reduce((sum, file) => sum + file.size, 0);
        const storage = await navigator.storage.estimate();
        if (storage.quota && storage.quota - storage.usage < totalBytes * 1.1)
            throw new Error("Browser storage is too small for the Pi's licensed RCT2 data.");
        let downloadedBytes = 0, lastProgress = 0;
        const showProgress = (force = false) => {
            const now = performance.now();
            if (!force && now - lastProgress < 200) return;
            lastProgress = now;
            setStatus(`Loading RCT2 assets… ${(downloadedBytes / 1048576).toFixed(1)} / ${(totalBytes / 1048576).toFixed(1)} MiB · ${completed}/${manifest.files.length} files`);
        };
        clearDirectory(fs, "/RCT");
        let completed = 0;
        showProgress(true);
        // Chromium can reject a single IndexedDB transaction containing the
        // full licensed installation. Commit small verified batches instead.
        const batches = [];
        let batch = [], batchBytes = 0;
        for (const file of manifest.files) {
            if (batch.length && (batchBytes + file.size > 64 * 1024 * 1024 || batch.length >= 256)) {
                batches.push(batch); batch = []; batchBytes = 0;
            }
            batch.push(file);
            batchBytes += file.size;
        }
        if (batch.length) batches.push(batch);
        for (const files of batches) {
            let next = 0;
            await Promise.all(Array.from({ length: 4 }, async () => {
                while (next < files.length) {
                    const file = files[next++];
                const url = "/private/rct2/files/" + file.path.split("/").map(encodeURIComponent).join("/");
                const response = await fetchRequired(url);
                const reader = response.body.getReader();
                const data = new Uint8Array(file.size);
                let offset = 0;
                try {
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        if (offset + value.byteLength > data.byteLength)
                            throw new Error(`RCT2 asset exceeds its manifest size: ${file.path}`);
                        data.set(value, offset);
                        offset += value.byteLength;
                        downloadedBytes += value.byteLength;
                        showProgress();
                    }
                } finally {
                    reader.releaseLock();
                }
                if (offset !== file.size)
                    throw new Error(`Incomplete RCT2 download: ${file.path}`);
                if (data.byteLength !== file.size || await hash(data) !== file.sha256)
                    throw new Error(`Private RCT2 asset differs from its manifest: ${file.path}`);
                const parts = file.path.split("/");
                let parent = "/RCT";
                for (const part of parts.slice(0, -1)) {
                    parent += `/${part}`;
                    ensureDir(fs, parent);
                }
                fs.writeFile(`${parent}/${parts.at(-1)}`, new Uint8Array(data));
                completed++;
                showProgress(true);
                }
            }));
            setStatus(`Saving RCT2 assets in the browser… ${completed}/${manifest.files.length} files`);
            await sync(fs, false);
            showProgress(true);
        }
        if (!fs.analyzePath("/RCT/Data/ch.dat").exists)
            throw new Error("The Pi's RCT2 installation is missing Data/ch.dat.");
        fs.writeFile("/RCT/starcoaster-licensed-version", manifest.version);
        setStatus("Saving RCT2 files in the browser…");
        await sync(fs, false);
    };

    try {
        if (!crossOriginIsolated || !SharedArrayBuffer)
            throw new Error("Cross-origin isolation is required. Serve with COOP: same-origin and COEP: require-corp over HTTPS or localhost.");
        if (!window.WebAssembly || !window.JSZip) throw new Error("WebAssembly or the local ZIP library is unavailable.");
        const manifest = await (await fetchRequired("manifest.json")).json();
        if (manifest.schema !== 1 || manifest.native_bridge_version !== 5 ||
            manifest.asset_version !== 4 || manifest.plugin_api_version !== 124 ||
            typeof manifest.network_enabled !== "boolean")
            throw new Error("Browser bundle compatibility version mismatch.");
        const script = document.createElement("script");
        script.src = "openrct2.js";
        await new Promise((resolve, reject) => {
            script.onload = resolve;
            script.onerror = () => reject(new Error("Cannot load openrct2.js"));
            document.body.appendChild(script);
        });
        if (typeof window.OPENRCT2_WEB !== "function") throw new Error("OpenRCT2 WASM factory is missing.");
        setStatus("Initializing the OpenRCT2 graphical engine…");
        const runtimeOptions = {
            noInitialRun: true, arguments: [], canvas,
            print: (line) => console.log(line),
            printErr: (line) => console.error(line),
            locateFile: (name) => name,
        };
        // Explicit test-only diagnostics. Emscripten reads ENV while the
        // factory starts, before the live harness can access Module.callMain.
        const diagnostics = new URLSearchParams(window.location.search);
        if (diagnostics.get("starcoaster-performance") === "1") {
            runtimeOptions.ENV = {
                STARCOASTER_PERF: diagnostics.get("starcoaster-performance-baseline") === "1" ? "0" : "1",
                STARCOASTER_SUPPRESS_PAINT: diagnostics.get("starcoaster-suppress-paint") === "1" ? "1" : "0",
            };
        }
        if (manifest.network_enabled) {
            const endpoint = new URL("/ws", window.location.href);
            endpoint.protocol = endpoint.protocol === "https:" ? "wss:" : "ws:";
            runtimeOptions.websocket = { url: endpoint.href, subprotocol: "binary" };
        }
        const module = await window.OPENRCT2_WEB(runtimeOptions);
        window.Module = module;
        const fs = module.FS;
        let sessionGeneration = "";
        let mapLoadPending = false;
        const sessionStatus = async () => {
            const response = await fetch("/private/park-session", { cache: "no-store" });
            if (!response.ok) throw new Error(`Session status: HTTP ${response.status}`);
            return response.json();
        };
        const sessionRequest = async (route, body, filename = "") => {
            const response = await fetch(`/private/park-session/${route}`, {
                method: "POST",
                headers: {
                    "Content-Type": route === "upload" ? "application/octet-stream" : "application/json",
                    ...(filename ? { "X-StarCoaster-Filename": filename } : {}),
                },
                body,
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.error || `${route}: HTTP ${response.status}`);
            return result;
        };
        let backendAvailable = false;
        try {
            const initialState = await sessionStatus();
            sessionGeneration = initialState.generation || "";
            backendAvailable = manifest.network_enabled;
        } catch (_) {}
        if (backendAvailable) {
            window.starcoasterMapLoad = (path, isScenario) => {
                if (mapLoadPending) return;
                const filename = path.split(/[\\/]/).pop();
                // The Emscripten file picker removes the temporary file as
                // soon as its callback returns, so copy bytes before awaiting.
                let saveBytes = null;
                try { if (!isScenario) saveBytes = fs.readFile(path); }
                catch (error) {
                    status.classList.add("error");
                    document.body.appendChild(status);
                    setStatus(`Cannot read selected save: ${error.message || error}`);
                    return;
                }
                mapLoadPending = true;
                status.classList.remove("error");
                document.body.appendChild(status);
                setStatus(`Preparing ${filename} on the authoritative host…`);
                (async () => {
                    const before = await sessionStatus();
                    let park = filename;
                    if (saveBytes) {
                        const suffix = filename.match(/\.(park|sc6|sc4|sv6|sv4)$/i)?.[0];
                        if (!suffix) throw new Error("Unsupported OpenRCT2 save format.");
                        const uploaded = await sessionRequest("upload", saveBytes, `selected${suffix}`);
                        park = uploaded.park;
                    }
                    await sessionRequest("load", JSON.stringify({park, decision: "discard", generation: before.generation || ""}));
                    const deadline = Date.now() + 240000;
                    while (Date.now() < deadline) {
                        await new Promise((resolve) => setTimeout(resolve, 500));
                        const current = await sessionStatus();
                        if (current.phase === "ready" && current.generation !== before.generation) {
                            if (current.current !== park || current.error)
                                throw new Error(current.error || `The host activated ${current.current} instead of ${park}.`);
                            sessionGeneration = current.generation;
                            setStatus("Joining authoritative OpenRCT2 session…");
                            module.ccall("StarCoasterJoin", null, [], []);
                            status.remove();
                            canvas.focus();
                            return;
                        }
                        if (current.error && (current.phase === "idle" || current.phase === "failed" ||
                            current.phase === "ready" && current.generation === before.generation))
                            throw new Error(current.error);
                    }
                    throw new Error("The authoritative game did not become ready in time.");
                })().catch((error) => {
                    status.classList.add("error");
                    setStatus(`StarCoaster synchronization failed: ${error.message || error}`);
                }).finally(() => { mapLoadPending = false; });
            };
            window.starcoasterReturnToTitle = () => {
                if (!sessionGeneration) return;
                sessionRequest("title", JSON.stringify({ generation: sessionGeneration }))
                    .then(() => {
                        sessionGeneration = "";
                        status.classList.remove("error");
                        status.remove();
                    })
                    .catch((error) => {
                        status.classList.add("error");
                        document.body.appendChild(status);
                        setStatus(`StarCoaster session cleanup failed: ${error.message || error}`);
                    });
            };
        }
        for (const path of ["/persistent", "/RCT", "/OpenRCT2"]) {
            ensureDir(fs, path);
            // The engine's user data changes during play. The two asset trees
            // are installed in batches and explicitly synced below; syncing
            // every extracted file makes large RCT2 imports prohibitively slow.
            fs.mount(fs.filesystems.IDBFS, { autoPersist: path === "/persistent" }, path);
        }
        await sync(fs, true);
        const assetVersion = manifest.artifacts["assets.zip"];
        let installedVersion = "";
        try { installedVersion = fs.readFile("/OpenRCT2/starcoaster-version", { encoding: "utf8" }); } catch (_) {}
        if (installedVersion !== assetVersion) {
            setStatus("Installing matching OpenRCT2 and StarCoaster assets…");
            const data = await (await fetchRequired("assets.zip")).arrayBuffer();
            if (await hash(data) !== manifest.artifacts["assets.zip"])
                throw new Error("Asset ZIP hash differs from the bundle manifest.");
            const zip = await JSZip.loadAsync(data);
            clearDirectory(fs, "/OpenRCT2");
            await extract(fs, zip, "/OpenRCT2/");
            fs.writeFile("/OpenRCT2/starcoaster-version", assetVersion);
            await sync(fs, false);
        }
        if (!fs.analyzePath("/OpenRCT2/g2.dat").exists)
            throw new Error("Patched g2.dat is missing from the installed assets.");
        const plugin = fs.readFile("/OpenRCT2/plugin/rts-bridge.js");
        if (await hash(plugin) !== manifest.plugin_sha256)
            throw new Error("StarCoaster plugin differs from the bundle manifest.");
        ensureDir(fs, "/persistent/plugin");
        fs.writeFile("/persistent/plugin/rts-bridge.js", plugin);
        await sync(fs, false);
        // The object index stores filesystem metadata that IDBFS can change
        // while restoring files. Rebuild it from the installed objects.
        if (fs.analyzePath("/persistent/objects.idx").exists)
            fs.unlink("/persistent/objects.idx");
        const rct2Manifest = await privateRct2Manifest();
        let installedRct2Version = "";
        try { installedRct2Version = fs.readFile("/RCT/starcoaster-licensed-version", { encoding: "utf8" }); } catch (_) {}
        if (rct2Manifest && (!fs.analyzePath("/RCT/Data/ch.dat").exists ||
            installedRct2Version !== rct2Manifest.version)) {
            await provisionPrivateRct2(fs, rct2Manifest);
        } else if (!fs.analyzePath("/RCT/Data/ch.dat").exists) {
            setStatus("Import your locally licensed RCT2 data to continue.");
            document.getElementById("import").style.display = "block";
            const folderButton = document.getElementById("rct2-folder");
            if (!window.showDirectoryPicker) folderButton.style.display = "none";
            const selection = await new Promise((resolve, reject) => {
                document.getElementById("rct2-file").onchange = (event) => resolve({ file: event.target.files[0] });
                folderButton.onclick = async () => {
                    try { resolve({ folder: await window.showDirectoryPicker() }); }
                    catch (error) { if (error.name !== "AbortError") reject(error); }
                };
            });
            setStatus("Importing your RCT2 files…");
            if (selection.folder) {
                let folder = selection.folder;
                try { await folder.getDirectoryHandle("Data"); }
                catch (_) {
                    try { folder = await folder.getDirectoryHandle("RCT"); }
                    catch (_) { throw new Error("RCT2 folder must contain Data/ch.dat or RCT/Data/ch.dat."); }
                }
                await importDirectory(fs, folder, "/RCT", { count: 0 });
            } else {
                if (!selection.file) throw new Error("No RCT2 data ZIP selected.");
                const zip = await JSZip.loadAsync(selection.file);
                const prefix = zip.file("Data/ch.dat") ? "" : zip.file("RCT/Data/ch.dat") ? "RCT/" : null;
                if (prefix === null) throw new Error("RCT2 ZIP must contain Data/ch.dat or RCT/Data/ch.dat.");
                const entries = new JSZip();
                for (const [name, entry] of Object.entries(zip.files)) {
                    if (name.startsWith(prefix)) entries.files[name.slice(prefix.length)] = entry;
                }
                await extract(fs, entries, "/RCT/");
            }
            if (!fs.analyzePath("/RCT/Data/ch.dat").exists)
                throw new Error("The selected RCT2 installation is missing Data/ch.dat.");
            setStatus("Saving RCT2 files in the browser…");
            await sync(fs, false);
            document.getElementById("import").style.display = "none";
        }
        setStatus("Starting OpenRCT2…");
        canvas.style.display = "block";
        // Explicit development runs may exercise the existing multiplayer
        // harness. Ordinary visits always enter OpenRCT2's main menu.
        const joinParams = new URLSearchParams(window.location.search);
        const testPort = Number(joinParams.get("starcoaster-test-port") || 11753);
        const startupArgs = manifest.network_enabled && joinParams.has("starcoaster-test-join")
            ? ["join", "127.0.0.1", `--port=${Number.isInteger(testPort) && testPort >= 1024 && testPort <= 65535 ? testPort : 11753}`] : [];
        startupArgs.push("--rct2-data-path=/RCT", "--user-data-path=/persistent/", "--openrct2-data-path=/OpenRCT2/");
        if (new URLSearchParams(window.location.search).has("verbose")) startupArgs.push("--verbose");
        module.callMain(startupArgs);
        status.remove();
        if (backendAvailable) {
            let watching = false;
            setInterval(async () => {
                if (watching || mapLoadPending) return;
                watching = true;
                try {
                    const state = await sessionStatus();
                    if (state.phase === "ready" && state.generation &&
                        state.generation !== sessionGeneration) {
                        sessionGeneration = state.generation;
                        status.classList.remove("error", "warning");
                        document.body.appendChild(status);
                        setStatus("Joining the new authoritative OpenRCT2 session…");
                        module.ccall("StarCoasterJoin", null, [], []);
                        if (state.error) {
                            status.classList.add("warning");
                            setStatus(`StarCoaster restored a prior game: ${state.error}`);
                        } else status.remove();
                        canvas.focus();
                    } else if (sessionGeneration && (state.phase === "failed" || state.phase === "idle")) {
                        status.classList.add("error");
                        document.body.appendChild(status);
                        setStatus(`StarCoaster synchronization stopped: ${state.error || "The authoritative session ended."}`);
                    }
                } catch (error) {
                    if (sessionGeneration) {
                        status.classList.add("error");
                        document.body.appendChild(status);
                        setStatus(`StarCoaster synchronization unavailable: ${error.message || error}`);
                    }
                } finally { watching = false; }
            }, 1500);
        }
        if (!backendAvailable && manifest.network_enabled) {
            status.classList.add("warning");
            setStatus("StarCoaster host unavailable. Local OpenRCT2 can load parks; StarCraft synchronization is offline.");
            document.body.appendChild(status);
        }
        canvas.focus();
    } catch (error) {
        fail(error);
    }
})();
