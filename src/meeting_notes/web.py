"""Local browser UI and API for the offline meeting-notes pipeline."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from mimetypes import guess_type
import json, threading
from uuid import uuid4
from .config import load_config
from .pipeline import apply_speaker_map, process_meeting

ALLOWED_AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".webm", ".ogg", ".opus", ".flac", ".aac"}
RESULT_FILES = ("transcript.md", "transcript.json", "summary_full.md", "summary_short.md", "actions.md", "actions.json", "speakers.json", "speaker-map.json")
MARKDOWN_FILES = {"transcript.md": "annotated_transcript", "summary_full.md": "full_summary", "summary_short.md": "short_summary", "actions.md": "actions"}

def _now():
    return datetime.now(timezone.utc).isoformat()

@dataclass
class Job:
    id: str
    input_path: Path
    status: str = "queued"
    message: str = "Waiting to start"
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None
    output_dir: Path | None = None
    markdown: dict[str, str] = field(default_factory=dict)
    speakers: list[dict] = field(default_factory=list)
    speaker_map: dict[str, str] = field(default_factory=dict)
    skipped_speakers: set[str] = field(default_factory=set)
    def as_dict(self):
        result = {"id": self.id, "status": self.status, "message": self.message, "created_at": self.created_at, "started_at": self.started_at, "finished_at": self.finished_at}
        if self.status == "completed":
            result["files"] = {name: f"/api/jobs/{self.id}/files/{name}" for name in RESULT_FILES}
            result["markdown"] = self.markdown
        elif self.status == "failed": result["error"] = self.message
        return result

def _web_dependencies():
    try:
        from fastapi import Body, FastAPI, File, HTTPException, UploadFile
        from fastapi.responses import FileResponse, HTMLResponse
    except ImportError as exc:
        raise RuntimeError("The local web UI requires optional dependencies. Install them with: pip install -e \".[web]\"") from exc
    return FastAPI, File, HTTPException, UploadFile, HTMLResponse, FileResponse, Body

def _suffix(filename, content_type, recording=False):
    suffix = Path(filename or "").suffix.lower(); ctype = (content_type or "").lower()
    if suffix not in ALLOWED_AUDIO_SUFFIXES:
        if recording and ctype in {"audio/webm", "video/webm"}: suffix = ".webm"
        elif recording and ctype in {"audio/ogg", "application/ogg"}: suffix = ".ogg"
        else: raise ValueError("Unsupported audio format. Use WAV, MP3, M4A, WebM, OGG, OPUS, FLAC, or AAC.")
    return suffix

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Offline Meeting Notes</title><style>body{font:16px system-ui;max-width:980px;margin:32px auto;padding:0 16px;background:#f4f7fa;color:#17212b}.card{background:#fff;border:1px solid #d9e1e8;border-radius:14px;padding:22px;margin:18px 0}button{background:#1769aa;color:white;border:0;border-radius:20px;padding:11px 20px;font-weight:bold;cursor:pointer}.hidden{display:none}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}.speaker{border:1px solid #d9e1e8;border-radius:10px;padding:14px}.speaker audio{width:100%;margin:10px 0}.speaker input{width:100%;padding:9px;box-sizing:border-box;margin:5px 0 8px}.hint{color:#637083}pre{white-space:pre-wrap;background:#f8fafc;padding:12px}</style></head><body><h1>Offline Meeting Notes</h1><p class="hint">Record or upload audio. Processing and speaker clips stay on this computer.</p><section class="card"><button id="record">Start recording</button><span id="record-hint" class="hint"> Microphone permission is required.</span></section><section class="card"><h2>Upload audio</h2><input id="file" type="file" accept="audio/*,.m4a,.webm,.ogg,.opus"></section><section id="job" class="card hidden"><b id="status"></b></section><section id="speakers" class="card hidden"><h2>Identify speakers</h2><p class="hint">Labels are per recording. Listen to each clip before entering a name; a later recording asks again. Previous names are quick-pick suggestions.</p><form id="speaker-form"><div id="speaker-list" class="grid"></div><datalist id="speaker-names"></datalist><button type="submit">Save names and update notes</button></form><p id="speaker-message" class="hint"></p></section><section id="results" class="card hidden"><h2>Meeting notes</h2><p id="links"></p><div class="grid"><article><h3>Short summary</h3><pre id="short_summary"></pre></article><article><h3>Full summary</h3><pre id="full_summary"></pre></article><article><h3>Actions</h3><pre id="actions"></pre></article><article><h3>Transcript</h3><pre id="annotated_transcript"></pre></article></div></section><script>
(()=>{const $=s=>document.querySelector(s),record=$("#record"),file=$("#file"),job=$("#job"),status=$("#status"),speakers=$("#speakers"),list=$("#speaker-list"),results=$("#results"),form=$("#speaker-form"),message=$("#speaker-message");let recorder,stream,chunks=[],timer,current;
function render(d){const names=$("#speaker-names");names.textContent="";(d.speaker_names||[]).forEach(n=>{const o=document.createElement("option");o.value=n;names.append(o)});const rows=d.speakers||[];speakers.classList.toggle("hidden",!d.needs_speaker_assignment);list.textContent="";rows.forEach(s=>{const r=document.createElement("article");r.className="speaker";const h=document.createElement("b");h.textContent=s.id;r.append(h);const a=document.createElement("audio");a.controls=true;a.src=s.clip_url;r.append(a);const p=document.createElement("p");p.className="hint";p.textContent=s.sample_text?"Sample: "+s.sample_text:"No transcript sample";r.append(p);const i=document.createElement("input");i.className="speaker-name";i.name=s.id;i.placeholder="Real name";i.value=s.name||"";i.setAttribute("list","speaker-names");i.required=!s.skipped;r.append(i);const l=document.createElement("label");const c=document.createElement("input");c.type="checkbox";c.className="speaker-skip";c.dataset.id=s.id;c.checked=!!s.skipped;c.onchange=()=>{i.disabled=c.checked;i.required=!c.checked};l.append(c,document.createTextNode(" Leave anonymous"));r.append(l);list.append(r)});message.textContent=d.needs_speaker_assignment?"Name every speaker or explicitly leave one anonymous.":"Speaker names saved."}
function show(d){Object.keys(d.markdown||{}).forEach(k=>$("#"+k).textContent=d.markdown[k]);$("#links").innerHTML=Object.entries(d.files||{}).map(([n,u])=>"<a href=\""+u+"\" download>"+n+"</a>").join(" · ");results.classList.remove("hidden");render(d)}
async function poll(id){const r=await fetch("/api/jobs/"+id),d=await r.json();current=d;status.textContent=d.message||d.status;if(d.status==="queued"||d.status==="running")return;clearInterval(timer);if(d.status==="failed"){status.textContent="Processing failed: "+d.error;return}show(d);status.textContent=d.needs_speaker_assignment?"Complete — identify speakers below.":"Complete."}
async function send(blob,name,url="/api/upload"){job.classList.remove("hidden");status.textContent="Uploading…";const f=new FormData;f.append("file",blob,name);const r=await fetch(url,{method:"POST",body:f}),d=await r.json();if(!r.ok){status.textContent=d.detail||"Upload failed";return}if(timer)clearInterval(timer);timer=setInterval(()=>poll(d.id),2000);poll(d.id)}
form.onsubmit=async e=>{e.preventDefault();const mapping={},skip=[];list.querySelectorAll(".speaker-name").forEach(i=>{const c=list.querySelector(".speaker-skip[data-id=\""+i.name+"\"]");if(c&&c.checked)skip.push(i.name);else mapping[i.name]=i.value.trim()});message.textContent="Saving and regenerating local notes…";const r=await fetch("/api/jobs/"+current.id+"/speakers",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({mapping,skip})}),d=await r.json();if(!r.ok){message.textContent=d.detail||"Could not save names";return}current=d;show(d);status.textContent=d.needs_speaker_assignment?"Some speakers still need names.":"Speaker names saved; notes updated."};
record.onclick=async()=>{if(recorder&&recorder.state==="recording"){recorder.stop();return}stream=await navigator.mediaDevices.getUserMedia({audio:true});const type=["audio/webm;codecs=opus","audio/webm","audio/ogg;codecs=opus"].find(t=>MediaRecorder.isTypeSupported(t));recorder=new MediaRecorder(stream,type?{mimeType:type}:undefined);chunks=[];recorder.ondataavailable=e=>e.data.size&&chunks.push(e.data);recorder.onstop=()=>{stream.getTracks().forEach(t=>t.stop());const b=new Blob(chunks,{type:recorder.mimeType||"audio/webm"});send(b,"recording.webm","/api/record/stop");record.textContent="Start recording"};recorder.start();record.textContent="Stop recording"};file.onchange=()=>file.files[0]&&send(file.files[0],file.files[0].name)})()</script></body></html>"""

def create_app(config_path=None, jobs_dir=".meeting-notes/jobs"):
    FastAPI, File, HTTPException, UploadFile, HTMLResponse, FileResponse, Body = _web_dependencies()
    root = Path(jobs_dir).expanduser().resolve(); uploads = root / "uploads"; outputs = root / "outputs"
    uploads.mkdir(parents=True, exist_ok=True); outputs.mkdir(parents=True, exist_ok=True)
    roster_path = root.parent / "speaker-roster.json"
    config = load_config(config_path); jobs = {}; lock = threading.Lock(); executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="meeting-notes")
    app = FastAPI(title="Offline Meeting Notes", docs_url="/api/docs", redoc_url=None); app.state.jobs_root = root
    def roster_names():
        try:
            data = json.loads(roster_path.read_text(encoding="utf-8")); values = data.get("names", []) if isinstance(data, dict) else data
            return sorted({str(v).strip() for v in values if str(v).strip()}, key=str.casefold)
        except (FileNotFoundError, json.JSONDecodeError, OSError): return []
    def save_roster(names):
        values = sorted(set(roster_names()) | {str(v).strip() for v in names if str(v).strip()}, key=str.casefold)
        temp = roster_path.with_suffix(".tmp"); temp.write_text(json.dumps({"names": values, "updated_at": _now()}, indent=2) + "\n", encoding="utf-8"); temp.replace(roster_path)
    def speaker_view(j):
        suggestions = roster_names()
        return [{**item, "clip_url": "/api/jobs/" + j.id + "/speakers/" + item["id"] + "/clip", "name": j.speaker_map.get(item["id"], ""), "skipped": item["id"] in j.skipped_speakers, "suggested_name": suggestions[0] if suggestions else None} for item in j.speakers]
    def snapshot(job_id):
        with lock:
            if job_id not in jobs: raise HTTPException(status_code=404, detail="Unknown job")
            j=jobs[job_id]; result=j.as_dict()
            if j.status=="completed":
                result.update({"speakers":speaker_view(j),"speaker_names":roster_names(),"needs_speaker_assignment":any(x["id"] not in j.speaker_map and x["id"] not in j.skipped_speakers for x in j.speakers)})
            return result
    def process(job_id):
        with lock: j=jobs[job_id]; j.status,j.message,j.started_at="running","Transcribing and generating notes locally…",_now()
        try:
            output=process_meeting(str(j.input_path),config,output_root=outputs); markdown={key:(output/filename).read_text(encoding="utf-8") for filename,key in MARKDOWN_FILES.items()}; data=json.loads((output/"speakers.json").read_text(encoding="utf-8"))
            with lock: j.output_dir,j.markdown,j.speakers,j.status,j.message,j.finished_at=output,markdown,data,"completed","Processing complete. Identify the speakers below.",_now()
        except Exception as exc:
            with lock: j.status,j.message,j.finished_at="failed",str(exc),_now()
    def submit(upload,recording=False):
        try: suffix=_suffix(upload.filename,upload.content_type,recording)
        except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc
        job_id=uuid4().hex; path=uploads/(job_id+suffix)
        with path.open("wb") as out:
            while chunk:=upload.file.read(1024*1024): out.write(chunk)
        with lock: jobs[job_id]=Job(job_id,path)
        executor.submit(process,job_id); return {"id":job_id,"status":"queued","message":"Job queued.","status_url":f"/api/jobs/{job_id}"}
    @app.get("/",response_class=HTMLResponse)
    async def index(): return HTMLResponse(PAGE)
    @app.post("/api/upload")
    async def upload(file:UploadFile=File(...)): return submit(file)
    @app.post("/api/record/stop")
    async def record_stop(file:UploadFile=File(...)): return submit(file,True)
    @app.get("/api/jobs/{job_id}")
    async def job_status(job_id:str): return snapshot(job_id)
    @app.post("/api/jobs/{job_id}/speakers")
    async def assign_speakers(job_id:str,payload:dict=Body(...)):
        with lock:
            j=jobs.get(job_id)
            if not j: raise HTTPException(status_code=404,detail="Unknown job")
            if j.status!="completed": raise HTTPException(status_code=409,detail="Speaker assignment is available after processing completes")
            valid={x["id"] for x in j.speakers}; raw=payload.get("mapping",payload) if isinstance(payload,dict) else {}; skip={str(x).strip() for x in payload.get("skip",[]) if str(x).strip() in valid}
            mapping={str(k).strip():str(v).strip() for k,v in raw.items() if str(k).strip() in valid and str(v).strip()}; missing=valid-set(mapping)-skip
            if missing: raise HTTPException(status_code=400,detail="Enter a name or choose Leave anonymous for: "+", ".join(sorted(missing)))
            output_dir=j.output_dir
        regenerated=apply_speaker_map(output_dir,mapping,config)
        with lock: j.speaker_map.update(mapping); j.skipped_speakers=skip; j.markdown={key:(output_dir/filename).read_text(encoding="utf-8") for filename,key in MARKDOWN_FILES.items()}; j.message="Speaker names saved; notes updated locally."
        save_roster(mapping.values()); result=snapshot(job_id); result["summaries_regenerated"]=regenerated; return result
    @app.get("/api/jobs/{job_id}/speakers/{speaker_id}/clip")
    async def speaker_clip(job_id:str,speaker_id:str):
        with lock:
            j=jobs.get(job_id); item=next((x for x in j.speakers if x["id"]==speaker_id),None) if j else None; path=j.output_dir/item["clip"] if j and item and j.output_dir else None
        if path is None or not path.is_file(): raise HTTPException(status_code=404,detail="Speaker clip not found")
        return FileResponse(path,media_type=guess_type(path.name)[0] or "audio/wav",filename=path.name)
    @app.get("/api/jobs/{job_id}/files/{name}")
    async def job_file(job_id:str,name:str):
        with lock: j=jobs.get(job_id); path=j.output_dir/name if j and j.output_dir else None
        if name not in RESULT_FILES or path is None or not path.is_file(): raise HTTPException(status_code=404,detail="File not found")
        return FileResponse(path,media_type=guess_type(name)[0] or "application/octet-stream",filename=name)
    return app

def run_server(host="127.0.0.1",port=8765,config_path=None,jobs_dir=".meeting-notes/jobs"):
    if host not in {"127.0.0.1","localhost","::1"}: raise ValueError("The offline web UI only binds to localhost (127.0.0.1, localhost, or ::1).")
    try: import uvicorn
    except ImportError as exc: raise RuntimeError("The local web UI requires optional dependencies. Install them with: pip install -e \".[web]\"") from exc
    uvicorn.run(create_app(config_path,jobs_dir),host=host,port=port)
