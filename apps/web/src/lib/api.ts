import { createClient } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

async function getToken(): Promise<string> {
  const { data, error } = await createClient().auth.getSession();
  if (error || !data.session?.access_token) throw new Error("Your session expired. Sign in again to continue.");
  return data.session.access_token;
}

export type DatasetUploadIntent={dataset_id:string;object_key:string;bucket:string;byte_size:number};
function uploadIntentKey(file:File):string{return `meridian-intent:${file.name}:${file.size}:${file.lastModified}`}

export function restoreDatasetUploadIntent(file:File):DatasetUploadIntent|null{try{const stored=localStorage.getItem(uploadIntentKey(file));return stored?JSON.parse(stored) as DatasetUploadIntent:null}catch{return null}}

export async function createDatasetUploadIntent(file:File):Promise<DatasetUploadIntent>{
  const intent=await api<DatasetUploadIntent>("/datasets/upload-intents",{method:"POST",body:JSON.stringify({filename:file.name,byte_size:file.size})});
  localStorage.setItem(uploadIntentKey(file),JSON.stringify(intent));
  return intent;
}

function encodeMetadata(value:string):string{return btoa(String.fromCharCode(...new TextEncoder().encode(value)))}

export async function uploadCsvResumable(file:File,intent:DatasetUploadIntent,onProgress:(percent:number)=>void):Promise<void>{
  const projectUrl=process.env.NEXT_PUBLIC_SUPABASE_URL;
  const apiKey=process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if(!projectUrl||!apiKey)throw new Error("Supabase browser configuration is missing.");
  const token=await getToken();
  const projectHost=new URL(projectUrl);
  const hostedProject=projectHost.hostname.match(/^([^.]+)\.supabase\.co$/);
  const derivedStorageUrl=hostedProject?`${projectHost.protocol}//${hostedProject[1]}.storage.supabase.co`:projectUrl;
  const storageBase=process.env.NEXT_PUBLIC_SUPABASE_STORAGE_URL||derivedStorageUrl;
  const endpoint=`${storageBase.replace(/\/$/,"")}/storage/v1/upload/resumable`;
  const key=`meridian-upload:${intent.dataset_id}:${file.size}:${file.lastModified}`;
  const requestHeaders={"Tus-Resumable":"1.0.0",apikey:apiKey,Authorization:`Bearer ${token}`};
  let uploadUrl=localStorage.getItem(key);
  let offset=0;
  if(uploadUrl){try{const head=await fetch(uploadUrl,{method:"HEAD",headers:requestHeaders});if(!head.ok)throw new Error("Expired upload session");offset=Number(head.headers.get("Upload-Offset")||0);if(offset>file.size)throw new Error("Invalid upload offset")}catch{localStorage.removeItem(key);uploadUrl=null;offset=0}}
  if(!uploadUrl){
    const metadata={bucketName:intent.bucket,objectName:intent.object_key,contentType:"text/csv",cacheControl:"3600"};
    const uploadMetadata=Object.entries(metadata).map(([name,value])=>`${name} ${encodeMetadata(value)}`).join(",");
    const created=await fetch(endpoint,{method:"POST",headers:{...requestHeaders,"Upload-Length":String(file.size),"Upload-Metadata":uploadMetadata,"x-upsert":"false"}});
    if(!created.ok)throw new Error(`Supabase resumable upload setup failed (${created.status}). Check the project's Storage limits and CORS settings.`);
    const location=created.headers.get("Location");if(!location)throw new Error("Supabase did not return a resumable upload location.");
    uploadUrl=new URL(location,endpoint).toString();
    if(new URL(uploadUrl).origin!==new URL(endpoint).origin)throw new Error("Supabase returned an unexpected upload location.");
    localStorage.setItem(key,uploadUrl);
  }
  const chunkSize=6*1024*1024;
  while(offset<file.size){
    const chunk=file.slice(offset,Math.min(offset+chunkSize,file.size));
    let response:Response|undefined;
    for(let attempt=0;attempt<5;attempt++){
      try{response=await fetch(uploadUrl,{method:"PATCH",headers:{...requestHeaders,"Upload-Offset":String(offset),"Content-Type":"application/offset+octet-stream"},body:chunk});if(response.ok)break;if(response.status===409){const head=await fetch(uploadUrl,{method:"HEAD",headers:requestHeaders});if(head.ok)offset=Number(head.headers.get("Upload-Offset")||offset)}if(response.status<500&&response.status!==409)throw new Error(`Upload chunk failed (${response.status}).`)}catch(error){if(attempt===4)throw error}
      await new Promise(resolve=>setTimeout(resolve,Math.min(1000*2**attempt,10000)));
    }
    if(!response?.ok)throw new Error("The upload connection failed after several retries.");
    const serverOffset=Number(response.headers.get("Upload-Offset")||offset+chunk.size);if(serverOffset<=offset||serverOffset>file.size)throw new Error("Supabase returned an invalid upload offset.");offset=serverOffset;onProgress(Math.round(offset/file.size*100));
  }
  await api(`/datasets/${intent.dataset_id}/complete-upload`,{method:"POST"});
  localStorage.removeItem(key);
  localStorage.removeItem(uploadIntentKey(file));
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await getToken();
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_URL}/api/v1${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try { const body = await response.json(); message = body.detail || message; } catch { /* use status fallback */ }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function uploadCsv(file: File, onProgress: (percent: number) => void): Promise<{dataset:{id:string};status:string}> {
  const token = await getToken();
  const form = new FormData(); form.append("file", file);
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/api/v1/datasets/upload`);
    xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = event => { if (event.lengthComputable) onProgress(Math.round(event.loaded / event.total * 100)); };
    xhr.onerror = () => reject(new Error("Upload failed. Check your connection and retry."));
    xhr.onload = () => {
      let body: { detail?: string; dataset?: { id: string }; status?: string } | null;
      try { body = JSON.parse(xhr.responseText) as typeof body; } catch { body = null; }
      if (xhr.status >= 200 && xhr.status < 300 && body?.dataset?.id && body.status) resolve({dataset:body.dataset,status:body.status});
      else reject(new Error(body?.detail || `Upload failed (${xhr.status}).`));
    };
    xhr.send(form);
  });
}
