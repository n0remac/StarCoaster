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
        status.classList.add("error");
        setStatus(`StarCoaster startup failed: ${error.message || error}`);
    };
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

    try {
        if (!crossOriginIsolated || !SharedArrayBuffer)
            throw new Error("Cross-origin isolation is required. Serve with COOP: same-origin and COEP: require-corp over HTTPS or localhost.");
        if (!window.WebAssembly || !window.JSZip) throw new Error("WebAssembly or the local ZIP library is unavailable.");
        const manifest = await (await fetchRequired("manifest.json")).json();
        if (manifest.schema !== 1 || manifest.native_bridge_version !== 5 ||
            manifest.asset_version !== 4 || manifest.plugin_api_version !== 124)
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
        const module = await window.OPENRCT2_WEB({
            noInitialRun: true, arguments: [], canvas,
            print: (line) => console.log(line),
            printErr: (line) => console.error(line),
            locateFile: (name) => name,
        });
        window.Module = module;
        const fs = module.FS;
        for (const path of ["/persistent", "/RCT", "/OpenRCT2"]) {
            ensureDir(fs, path);
            fs.mount(fs.filesystems.IDBFS, { autoPersist: true }, path);
        }
        await sync(fs, true);
        const assetVersion = `${manifest.openrct2_commit}:${manifest.patch_sha256}:${manifest.artifacts["assets.zip"]}`;
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
        if (!fs.analyzePath("/RCT/Data/ch.dat").exists) {
            setStatus("Import your locally licensed RCT2 data to continue.");
            document.getElementById("import").style.display = "block";
            const file = await new Promise((resolve) => {
                document.getElementById("rct2-file").onchange = (event) => resolve(event.target.files[0]);
            });
            if (!file) throw new Error("No RCT2 data ZIP selected.");
            const zip = await JSZip.loadAsync(file);
            const prefix = zip.file("Data/ch.dat") ? "" : zip.file("RCT/Data/ch.dat") ? "RCT/" : null;
            if (prefix === null) throw new Error("RCT2 ZIP must contain Data/ch.dat or RCT/Data/ch.dat.");
            const entries = new JSZip();
            for (const [name, entry] of Object.entries(zip.files)) {
                if (name.startsWith(prefix)) entries.files[name.slice(prefix.length)] = entry;
            }
            await extract(fs, entries, "/RCT/");
            await sync(fs, false);
            document.getElementById("import").style.display = "none";
        }
        setStatus("Starting OpenRCT2…");
        canvas.style.display = "block";
        module.callMain(["--rct2-data-path=/RCT", "--user-data-path=/persistent/", "--openrct2-data-path=/OpenRCT2/"]);
        status.remove();
        canvas.focus();
    } catch (error) {
        fail(error);
    }
})();
