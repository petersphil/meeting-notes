"""Local browser UI and API for the offline meeting-notes pipeline."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from mimetypes import guess_type
import threading
from uuid import uuid4

from .config import load_config
from .pipeline import process_meeting

ALLOWED_AUDIO_SUFFIXES = {'.wav', '.mp3', '.m4a', '.webm', '.ogg', '.opus', '.flac', '.aac'}
RESULT_FILES = ('transcript.md', 'transcript.json', 'summary_full.md', 'summary_short.md', 'actions.md', 'actions.json')
MARKDOWN_FILES = {'transcript.md': 'annotated_transcript', 'summary_full.md': 'full_summary', 'summary_short.md': 'short_summary', 'actions.md': 'actions'}


def _now():
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    id: str
    input_path: Path
    status: str = 'queued'
    message: str = 'Waiting to start'
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None
    output_dir: Path | None = None
    markdown: dict[str, str] = field(default_factory=dict)

    def as_dict(self):
        result = {'id': self.id, 'status': self.status, 'message': self.message, 'created_at': self.created_at, 'started_at': self.started_at, 'finished_at': self.finished_at}
        if self.status == 'completed':
            result['files'] = {name: f'/api/jobs/{self.id}/files/{name}' for name in RESULT_FILES}
            result['markdown'] = self.markdown
        elif self.status == 'failed':
            result['error'] = self.message
        return result


def _web_dependencies():
    try:
        from fastapi import FastAPI, File, HTTPException, UploadFile
        from fastapi.responses import HTMLResponse, StreamingResponse
    except ImportError as exc:
        raise RuntimeError("The local web UI requires optional dependencies. Install them with: pip install -e '.[web]'") from exc
    return FastAPI, File, HTTPException, UploadFile, HTMLResponse, StreamingResponse


def _suffix(filename, content_type, recording=False):
    suffix = Path(filename or '').suffix.lower()
    ctype = (content_type or '').lower()
    if suffix not in ALLOWED_AUDIO_SUFFIXES:
        if recording and ctype in {'audio/webm', 'video/webm'}: suffix = '.webm'
        elif recording and ctype in {'audio/ogg', 'application/ogg'}: suffix = '.ogg'
        else: raise ValueError('Unsupported audio format. Use WAV, MP3, M4A, WebM, OGG, OPUS, FLAC, or AAC.')
    return suffix

PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Offline Meeting Notes</title>
<style>
:root{color-scheme:light;--ink:#17212b;--muted:#637083;--line:#d9e1e8;--accent:#1769aa;--soft:#f4f7fa}
*{box-sizing:border-box}body{margin:0;background:var(--soft);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{width:min(980px,calc(100% - 32px));margin:36px auto 72px}h1{margin:0 0 8px;font-size:clamp(2rem,5vw,3rem);letter-spacing:-.03em}h2{margin-top:0}.lead,.hint{color:var(--muted)}
.card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:24px;margin:18px 0;box-shadow:0 5px 20px #18334d0b}.record{text-align:center;padding:32px 24px}
button{border:0;border-radius:999px;padding:13px 23px;background:var(--accent);color:#fff;font-weight:700;font-size:1rem;cursor:pointer}button.recording{background:#b42318}
.drop{display:block;border:2px dashed #b6c6d5;border-radius:12px;padding:30px;text-align:center;cursor:pointer;background:#fbfdff}.drop input{display:none}.hidden{display:none}
.progress{height:8px;background:#e6edf3;border-radius:8px;overflow:hidden;margin-top:13px}.progress:after{content:"";display:block;width:35%;height:100%;background:var(--accent);animation:slide 1.3s infinite ease-in-out}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.55 ui-monospace,monospace;max-height:420px;overflow:auto;background:#f8fafc;padding:12px;border-radius:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:16px}.result{border:1px solid var(--line);border-radius:12px;padding:16px}.result h3{margin:0 0 8px}a{color:var(--accent)}
@keyframes slide{0%{transform:translateX(-120%)}100%{transform:translateX(350%)}}
</style></head><body><main>
<h1>Offline Meeting Notes</h1><p class="lead">Record from this browser or choose an audio file. Processing stays on this computer.</p>
<section class="card record"><button id="record">Start recording</button><p id="record-hint" class="hint">Your browser will ask for microphone permission.</p></section>
<section class="card"><h2>Upload an audio file</h2><label class="drop" id="drop" for="file"><strong>Drop an audio file here</strong> or click to browse<div class="hint">WAV, MP3, M4A, WebM, OGG, OPUS, FLAC, or AAC</div><input id="file" type="file" accept="audio/*,.m4a,.webm,.ogg,.opus"></label></section>
<section id="job" class="card hidden" aria-live="polite"><h2>Processing</h2><div id="status">Starting…</div><div id="progress" class="progress"></div></section>
<section id="results" class="card hidden"><h2>Meeting notes</h2><p id="links"></p><div class="grid"><article class="result"><h3>Short summary</h3><pre id="short_summary"></pre></article><article class="result"><h3>Full summary</h3><pre id="full_summary"></pre></article><article class="result"><h3>Actions</h3><pre id="actions"></pre></article><article class="result"><h3>Annotated transcript</h3><pre id="annotated_transcript"></pre></article></div></section>
</main>
<script>
(()=>{const $=s=>document.querySelector(s),record=$('#record'),hint=$('#record-hint'),file=$('#file'),drop=$('#drop'),job=$('#job'),status=$('#status'),progress=$('#progress'),results=$('#results');let recorder,stream,chunks=[],timer;
function show(id){job.classList.remove('hidden');results.classList.add('hidden');status.textContent='Job '+id+' queued…';progress.classList.remove('hidden');if(timer)clearInterval(timer);timer=setInterval(()=>poll(id),2000);poll(id)}
async function send(blob,url,name){job.classList.remove('hidden');results.classList.add('hidden');status.textContent='Uploading…';try{const f=new FormData;f.append('file',blob,name);const r=await fetch(url,{method:'POST',body:f}),d=await r.json();if(!r.ok)throw Error(d.detail||'Upload failed');show(d.id)}catch(e){progress.classList.add('hidden');status.textContent='Error: '+e.message}}
async function poll(id){try{const r=await fetch('/api/jobs/'+encodeURIComponent(id)),d=await r.json();if(!r.ok)throw Error(d.detail||'Status request failed');status.textContent=d.message||d.status;if(d.status==='queued'||d.status==='running')return;clearInterval(timer);progress.classList.add('hidden');if(d.status==='failed'){status.textContent='Processing failed: '+d.error;return}status.textContent='Complete.';results.classList.remove('hidden');Object.keys(d.markdown||{}).forEach(k=>$('#'+k).textContent=d.markdown[k]);$('#links').innerHTML=Object.entries(d.files||{}).map(([n,u])=>'<a href="'+u+'" download>'+n+'</a>').join(' · ')}catch(e){status.textContent='Status error: '+e.message}}
record.onclick=async()=>{if(recorder&&recorder.state==='recording'){recorder.stop();return}try{stream=await navigator.mediaDevices.getUserMedia({audio:true});const type=['audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus','audio/ogg'].find(t=>MediaRecorder.isTypeSupported(t));recorder=new MediaRecorder(stream,type?{mimeType:type}:undefined);chunks=[];recorder.ondataavailable=e=>e.data.size&&chunks.push(e.data);recorder.onstop=()=>{stream.getTracks().forEach(t=>t.stop());const b=new Blob(chunks,{type:recorder.mimeType||'audio/webm'});send(b,'/api/record/stop',b.type.includes('ogg')?'recording.ogg':'recording.webm');record.textContent='Start recording';record.classList.remove('recording');hint.textContent='Recording uploaded; processing will continue locally.'};recorder.start();record.textContent='Stop recording';record.classList.add('recording');hint.textContent='Recording locally… click Stop when finished.'}catch(e){hint.textContent='Microphone could not be opened: '+e.message}};
file.onchange=()=>file.files[0]&&send(file.files[0],'/api/upload',file.files[0].name||'audio.wav');
['dragenter','dragover'].forEach(x=>drop.addEventListener(x,e=>{e.preventDefault();drop.style.borderColor='var(--accent)'}));['dragleave','drop'].forEach(x=>drop.addEventListener(x,e=>{e.preventDefault();drop.style.borderColor=''}));drop.ondrop=e=>e.dataTransfer.files[0]&&send(e.dataTransfer.files[0],'/api/upload',e.dataTransfer.files[0].name||'audio.wav')})();
</script></body></html>'''


def create_app(config_path=None, jobs_dir='.meeting-notes/jobs'):
    FastAPI, File, HTTPException, UploadFile, HTMLResponse, StreamingResponse = _web_dependencies()
    root=Path(jobs_dir).expanduser().resolve(); uploads=root/'uploads'; outputs=root/'outputs'
    uploads.mkdir(parents=True,exist_ok=True); outputs.mkdir(parents=True,exist_ok=True)
    config=load_config(config_path); jobs={}; lock=threading.Lock(); executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='meeting-notes')
    app=FastAPI(title='Offline Meeting Notes',docs_url='/api/docs',redoc_url=None); app.state.jobs_root=root

    def snapshot(job_id):
        with lock:
            if job_id not in jobs: raise HTTPException(status_code=404,detail='Unknown job')
            return jobs[job_id].as_dict()

    def process(job_id):
        with lock:
            job=jobs[job_id]; job.status,job.message,job.started_at='running','Transcribing and generating notes locally…',_now()
        try:
            output=process_meeting(str(job.input_path),config,output_root=outputs)
            markdown={key:(output/filename).read_text(encoding='utf-8') for filename,key in MARKDOWN_FILES.items()}
            with lock:
                job.output_dir,job.markdown,job.status,job.message,job.finished_at=output,markdown,'completed','Processing complete.',_now()
        except Exception as exc:
            with lock: job.status,job.message,job.finished_at='failed',str(exc),_now()

    def submit(upload,recording=False):
        try: suffix=_suffix(upload.filename,upload.content_type,recording)
        except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc
        job_id=uuid4().hex; path=uploads/(job_id+suffix)
        with path.open('wb') as out:
            while chunk:=upload.file.read(1024*1024): out.write(chunk)
        with lock: jobs[job_id]=Job(job_id,path)
        executor.submit(process,job_id)
        return {'id':job_id,'status':'queued','message':'Job queued.','status_url':f'/api/jobs/{job_id}'}

    @app.get('/',response_class=HTMLResponse)
    async def index(): return HTMLResponse(PAGE)
    @app.post('/api/upload')
    async def upload(file: UploadFile=File(...)): return submit(file)
    @app.post('/api/record/stop')
    async def record_stop(file: UploadFile=File(...)): return submit(file,True)
    @app.get('/api/jobs/{job_id}')
    async def job_status(job_id: str): return snapshot(job_id)
    @app.get('/api/jobs/{job_id}/files/{name}')
    async def job_file(job_id: str,name: str):
        with lock:
            job=jobs.get(job_id); path=job.output_dir/name if job and job.output_dir else None
        if name not in RESULT_FILES or path is None or not path.is_file(): raise HTTPException(status_code=404,detail='File not found')
        return StreamingResponse(path.open('rb'),media_type=guess_type(name)[0] or 'application/octet-stream',headers={'Content-Disposition':f'attachment; filename="{name}"'})
    return app


def run_server(host='127.0.0.1',port=8765,config_path=None,jobs_dir='.meeting-notes/jobs'):
    if host not in {'127.0.0.1','localhost','::1'}: raise ValueError('The offline web UI only binds to localhost (127.0.0.1, localhost, or ::1).')
    try: import uvicorn
    except ImportError as exc: raise RuntimeError("The local web UI requires optional dependencies. Install them with: pip install -e '.[web]'") from exc
    uvicorn.run(create_app(config_path,jobs_dir),host=host,port=port)
