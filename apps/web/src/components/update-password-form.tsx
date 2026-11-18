"use client";
import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
export function UpdatePasswordForm(){
 const [password,setPassword]=useState("");const [error,setError]=useState("");const [done,setDone]=useState(false);const [busy,setBusy]=useState(false);const router=useRouter();
 async function submit(e:FormEvent){e.preventDefault();setBusy(true);setError("");try{const {error:authError}=await createClient().auth.updateUser({password});if(authError)throw authError;setDone(true);router.refresh()}catch(cause){setError(cause instanceof Error?cause.message:"Password update failed.")}finally{setBusy(false)}}
 return <div className="auth-shell"><section className="auth-form-wrap"><div className="auth-form"><Link href="/sign-in" className="brand"><span className="brand-mark">M</span><span>Meridian<span style={{color:"#146b54"}}>.</span></span></Link><h1 className="auth-title">Choose a new password</h1><p className="auth-subtitle">Use at least 8 characters for your account password.</p>{done?<div role="status" style={{color:"#146b54",fontSize:14}}>Password updated. <Link className="text-link" href="/overview">Continue to your workspace</Link></div>:<form onSubmit={submit}><div className="field"><label htmlFor="new-password">New password</label><input id="new-password" type="password" autoComplete="new-password" minLength={8} required value={password} onChange={e=>setPassword(e.target.value)}/></div>{error&&<p role="alert" style={{color:"#b42318",fontSize:13}}>{error}</p>}<button className="primary-btn" disabled={busy}>{busy?"Updating…":"Update password"}</button></form>}</div></section><aside className="auth-art"><div className="art-eyebrow">Secure access</div><h2 className="art-title">Your data,<br/>under your control.</h2><p className="art-copy">Your account protects your workspace and the datasets you choose to upload.</p></aside></div>
}
