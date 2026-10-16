import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity, AlertTriangle, ArrowRight, BookOpen, Box, Braces, Bug, Check,
  ChevronDown, ChevronRight, CircleDot, Code2, FileCode2, Files, GitBranch,
  GitFork, LayoutDashboard, LoaderCircle, Moon, Play, Plus, Search, Settings,
  ShieldCheck, Sparkles, Sun, TestTube2, TerminalSquare, X
} from "lucide-react";
import { api, Repository, ReportSummary, Run, TestRun } from "./api";
import "./styles.css";

type View = "dashboard" | "repository" | "analysis" | "debug" | "tests" | "reports";

const samplePath = "/workspace/examples/sample-python-project";

function App() {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [view, setView] = useState<View>("dashboard");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [analysis, setAnalysis] = useState<Run | null>(null);
  const [debugRun, setDebugRun] = useState<Run | null>(null);
  const [problem, setProblem] = useState("Find the cause of the failing login functionality and generate a regression test.");
  const [showImport, setShowImport] = useState(false);
  const [source, setSource] = useState(samplePath);
  const [sourceType, setSourceType] = useState<"local" | "github">("local");
  const [dark, setDark] = useState(true);

  const selected = useMemo(() => repos.find(r => r.id === selectedId) || repos[0], [repos, selectedId]);

  const refresh = () => api.repositories().then(items => {
    setRepos(items);
    if (!selectedId && items.length) {
      setSelectedId((items.find(item => item.status === "ready") || items.find(item => item.status === "imported") || items[0]).id);
    }
  }).catch(e => setError(e.message));
  useEffect(() => { void refresh(); }, []);

  async function importRepo() {
    setBusy("Importing repository"); setError("");
    try {
      const repo = sourceType === "local" ? await api.addLocal(source) : await api.addGithub(source);
      const scanned = await api.scan(repo.id);
      setRepos(current => [scanned, ...current]); setSelectedId(scanned.id);
      setShowImport(false); setView("repository");
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(""); }
  }

  async function runAnalysis() {
    if (!selected) return;
    setBusy("Analyzing repository"); setError("");
    try { setAnalysis(await api.analyze(selected.id)); setView("analysis"); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(""); }
  }

  async function investigate() {
    if (!selected) return;
    setBusy("Running investigation"); setError(""); setDebugRun(null);
    try { setDebugRun(await api.debug(selected.id, problem)); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(""); }
  }

  const nav = [
    ["dashboard", LayoutDashboard, "Overview"], ["repository", Files, "Repository"],
    ["analysis", ShieldCheck, "Analysis"], ["debug", Bug, "Debug Lab"],
  ] as const;

  return <div className={dark ? "app dark" : "app"}>
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><GitBranch size={20}/></div><span>RepoWise</span></div>
      <nav>
        <p className="eyebrow">Workspace</p>
        {nav.map(([key, Icon, label]) => <button key={key} className={view === key ? "nav-item active" : "nav-item"} onClick={() => setView(key)}>
          <Icon size={17}/><span>{label}</span>{key === "analysis" && analysis && <i>{analysis.result.summary?.total || 0}</i>}
        </button>)}
        <p className="eyebrow second">Manage</p>
        <button className={view === "tests" ? "nav-item active" : "nav-item"} onClick={() => setView("tests")}><TestTube2 size={17}/><span>Test runs</span></button>
        <button className={view === "reports" ? "nav-item active" : "nav-item"} onClick={() => setView("reports")}><BookOpen size={17}/><span>Reports</span></button>
      </nav>
      <div className="sidebar-foot">
        <div className="system-status"><span className="pulse"/><div><strong>System ready</strong><small>Deterministic engine</small></div></div>
        <button className="nav-item"><Settings size={17}/><span>Settings</span></button>
      </div>
    </aside>

    <main>
      <header className="topbar">
        <div className="repo-switch"><span className="repo-glyph"><Braces size={16}/></span><div><small>Active repository</small><strong>{selected?.name || "No repository"}</strong></div><ChevronDown size={15}/></div>
        <div className="top-actions"><button className="icon-btn"><Search size={17}/></button><button className="icon-btn" onClick={() => setDark(!dark)}>{dark ? <Sun size={17}/> : <Moon size={17}/>}</button><button className="primary compact" onClick={() => setShowImport(true)}><Plus size={16}/> Add repository</button></div>
      </header>

      {error && <div className="toast error"><AlertTriangle size={17}/><span>{error}</span><button onClick={() => setError("")}><X size={16}/></button></div>}
      {busy && <div className="progress-bar"><span/></div>}

      <div className="page">
        {view === "dashboard" && <Dashboard repos={repos} selected={selected} setView={setView} onAdd={() => setShowImport(true)} onAnalyze={runAnalysis}/>} 
        {view === "repository" && <RepositoryPage repo={selected} onAnalyze={runAnalysis}/>} 
        {view === "analysis" && <AnalysisPage run={analysis} onRun={runAnalysis} busy={!!busy}/>} 
        {view === "debug" && <DebugPage repo={selected} problem={problem} setProblem={setProblem} run={debugRun} onRun={investigate} busy={!!busy}/>} 
        {view === "tests" && <TestRunsPage repo={selected} onError={setError}/>} 
        {view === "reports" && <ReportsPage repo={selected} onError={setError}/>} 
      </div>
    </main>

    {showImport && <div className="modal-backdrop" onMouseDown={() => setShowImport(false)}><section className="modal" onMouseDown={e => e.stopPropagation()}>
      <button className="modal-close" onClick={() => setShowImport(false)}><X size={18}/></button>
      <div className="modal-icon"><GitBranch size={22}/></div><h2>Connect a repository</h2><p>RepoWise will build a code-aware index without reading secrets or generated files.</p>
      <div className="segmented"><button className={sourceType === "local" ? "active" : ""} onClick={() => {setSourceType("local"); setSource(samplePath)}}>Local path</button><button className={sourceType === "github" ? "active" : ""} onClick={() => {setSourceType("github"); setSource("https://github.com/")}}><GitFork size={15}/> GitHub</button></div>
      <label>{sourceType === "local" ? "Absolute repository path" : "Public GitHub URL"}<input value={source} onChange={e => setSource(e.target.value)} /></label>
      <div className="security-note"><ShieldCheck size={17}/><span>Secrets, binaries, dependencies, and build artifacts are excluded automatically.</span></div>
      <button className="primary full" onClick={importRepo} disabled={!!busy}>{busy ? <LoaderCircle className="spin" size={17}/> : <ArrowRight size={17}/>} Import and scan</button>
    </section></div>}
  </div>;
}

function Dashboard({repos, selected, setView, onAdd, onAnalyze}: {repos: Repository[]; selected?: Repository; setView:(v:View)=>void; onAdd:()=>void; onAnalyze:()=>void}) {
  const p = selected?.profile || {};
  return <>
    <div className="hero-row"><div><span className="kicker"><Sparkles size={14}/> Repository intelligence</span><h1>Good morning, engineer.</h1><p>Inspect, investigate, and verify your codebase with evidence.</p></div><button className="primary" onClick={onAnalyze} disabled={!selected}><Play size={16}/> Run analysis</button></div>
    {!repos.length ? <div className="empty"><div className="empty-visual"><Code2 size={34}/><span/><span/><span/></div><h2>Bring your first repository into focus</h2><p>Import the included sample project or connect a public GitHub repository to begin.</p><button className="primary" onClick={onAdd}><Plus size={16}/> Add repository</button></div> : <>
      <section className="metric-grid">
        <Metric icon={Files} label="Source files" value={p.source_files ?? "—"} delta={`${p.statistics?.lines ?? 0} lines indexed`}/>
        <Metric icon={CircleDot} label="Open findings" value="—" delta="Run analysis to inspect"/>
        <Metric icon={TestTube2} label="Test files" value={p.test_files ?? "—"} delta="Detected automatically"/>
        <Metric icon={Activity} label="Index coverage" value={p.indexed_chunks ? "100%" : "—"} delta={`${p.indexed_chunks ?? 0} semantic chunks`}/>
      </section>
      <section className="dashboard-grid">
        <div className="panel activity-panel"><PanelTitle title="Engineering loop" subtitle="Your repository, reduced to inspectable steps"/>
          <div className="loop-track">{[["01","Understand","Structure mapped"],["02","Retrieve","Symbols indexed"],["03","Analyze","Evidence collected"],["04","Verify","Tests decide"]].map((x,i)=><React.Fragment key={x[0]}><div className="loop-node"><span>{x[0]}</span><strong>{x[1]}</strong><small>{x[2]}</small></div>{i<3&&<ChevronRight size={16}/>}</React.Fragment>)}</div>
        </div>
        <div className="panel repo-panel"><PanelTitle title="Active repository" subtitle="Ready for inspection"/>
          <div className="repo-card"><div className="repo-main"><span className="repo-big"><Braces size={22}/></span><div><strong>{selected?.name}</strong><small>{selected?.source}</small></div><span className="status"><Check size={12}/> {selected?.status}</span></div>
            <div className="tech-row">{(p.languages || []).map((l:any)=><span key={l.name}><i className={`dot ${l.name.toLowerCase()}`}/>{l.name}</span>)}{(p.frameworks||[]).map((f:string)=><span key={f}>{f}</span>)}</div>
            <button className="text-btn" onClick={()=>setView("repository")}>Open repository <ArrowRight size={14}/></button></div>
        </div>
      </section>
    </>}
  </>;
}

function Metric({icon:Icon,label,value,delta}:{icon:any;label:string;value:any;delta:string}) { return <div className="metric"><span className="metric-icon"><Icon size={18}/></span><div><small>{label}</small><strong>{value}</strong><p>{delta}</p></div></div> }
function PanelTitle({title,subtitle}:{title:string;subtitle:string}) { return <div className="panel-title"><div><h3>{title}</h3><p>{subtitle}</p></div><button className="dots">•••</button></div> }

function RepositoryPage({repo,onAnalyze}:{repo?:Repository;onAnalyze:()=>void}) {
  if (!repo) return <Blank title="No repository selected"/>;
  const p=repo.profile||{};
  return <><div className="page-head"><div><span className="breadcrumb">Repositories <ChevronRight size={13}/> {repo.name}</span><h1>{repo.name}</h1><p>{repo.source}</p></div><button className="primary" onClick={onAnalyze}><ShieldCheck size={16}/> Analyze code</button></div>
    <div className="summary-strip"><div><span>Status</span><strong className="green"><span className="pulse"/> {repo.status}</strong></div><div><span>Languages</span><strong>{(p.languages||[]).map((x:any)=>x.name).join(", ")||"—"}</strong></div><div><span>Package manager</span><strong>{p.package_manager||"—"}</strong></div><div><span>Indexed symbols</span><strong>{p.indexed_chunks||0}</strong></div></div>
    <div className="repository-layout"><section className="panel file-panel"><PanelTitle title="Architecture" subtitle={`${p.statistics?.files||0} files · ${p.statistics?.lines||0} lines`}/><FileTree profile={p}/></section>
      <section className="stack"><div className="panel"><PanelTitle title="Technology profile" subtitle="Detected from manifests and source"/><div className="tech-cards">{(p.languages||[]).map((l:any)=><div key={l.name}><FileCode2 size={18}/><strong>{l.name}</strong><small>{l.files} source files</small></div>)}</div></div>
      <div className="panel"><PanelTitle title="Entry points" subtitle="Likely application boundaries"/><div className="path-list">{(p.entry_points||[]).map((x:string)=><p key={x}><Code2 size={15}/><code>{x}</code></p>)}{!p.entry_points?.length&&<p className="muted">No conventional entry point detected.</p>}</div></div></section></div></>;
}

function FileTree({profile}:{profile:any}) { const dirs=profile.important_directories||[]; return <div className="tree"><div className="tree-line root"><ChevronDown size={15}/><Box size={16}/><strong>{profile.project_name}</strong></div>{dirs.map((d:string)=><div className="tree-line indent" key={d}><ChevronRight size={15}/><span className="folder"/><span>{d}</span></div>)}{(profile.configuration_files||[]).slice(0,8).map((f:string)=><div className="tree-line indent" key={f}><FileCode2 size={15}/><span>{f}</span><small>config</small></div>)}</div> }

function AnalysisPage({run,onRun,busy}:{run:Run|null;onRun:()=>void;busy:boolean}) {
  if(!run) return <div className="empty"><div className="empty-visual"><ShieldCheck size={34}/><span/><span/><span/></div><h2>No analysis has run yet</h2><p>Combine deterministic checks with code-aware context to surface actionable findings.</p><button className="primary" onClick={onRun} disabled={busy}><Play size={16}/> Run analysis</button></div>;
  const issues=run.result.issues||[];
  const summary=run.result.summary||{};
  return <><div className="page-head"><div><span className="kicker"><ShieldCheck size={14}/> Analysis #{run.id}</span><h1>Code health findings</h1><p>Evidence-backed findings, ordered by engineering impact.</p></div><button className="secondary" onClick={onRun}><Play size={16}/> Run again</button></div>
    <div className="analysis-summary"><div className={`risk-orb ${summary.risk_level||"none"}`}><strong>{String(summary.risk_level||"clear").toUpperCase()}</strong><span>Observed risk</span></div><div><h3>{issues.length ? `${issues.length} finding${issues.length===1?"":"s"} need attention` : "No deterministic findings"}</h3><p>{summary.executive_summary || "Review the evidence before accepting any suggested change."}</p><div className="severity-legend"><span className="critical">{issues.filter((i:any)=>i.severity==="critical").length} critical</span><span className="high">{issues.filter((i:any)=>i.severity==="high").length} high</span><span className="medium">{issues.filter((i:any)=>i.severity==="medium").length} medium</span></div></div></div>
    <section className="insight-strip"><div><span>Affected surface</span><strong>{summary.affected_files?.length||0} file{summary.affected_files?.length===1?"":"s"}</strong><p>{summary.affected_files?.slice(0,2).join(", ")||"No affected files"}</p></div><div><span>Test posture</span><strong>{summary.test_posture?.test_files||0} tests / {summary.test_posture?.source_files||0} source</strong><p>{summary.test_posture?.assessment||"Test coverage was not assessed."}</p></div><div><span>First priority</span><strong>{summary.priority_actions?.[0]?.title||"No action required"}</strong><p>{summary.priority_actions?.[0]?.action||"Continue monitoring the repository."}</p></div></section>
    <div className="section-label"><span>Detailed findings</span><small>facts, impact, remediation, and verification guidance</small></div>
    <div className="issue-list">{issues.map((issue:any,i:number)=><article className="issue detailed" key={i}><span className={`severity-bar ${issue.severity}`}/><div className="issue-body"><div className="issue-top"><span className={`badge ${issue.severity}`}>{issue.severity}</span><span className="category">{issue.category}</span><code>{displayPath(issue.file)}:{issue.line}</code></div><h3>{issue.title}</h3><p className="finding-summary">{issue.explanation}</p><div className="finding-grid"><div><span>Why this matters</span><p>{issue.why_it_matters}</p></div><div><span>Realistic failure scenario</span><p>{issue.failure_scenario}</p></div></div>{!!issue.code_excerpt?.length&&<div className="source-excerpt compact-source"><div className="source-title"><Code2 size={14}/><span>Observed source</span><code>{displayPath(issue.file)}</code></div>{issue.code_excerpt.map((line:any)=><div className={line.highlighted?"source-line highlighted":"source-line"} key={line.line}><span>{line.line}</span><code>{line.text||" "}</code>{line.highlighted&&<i>finding</i>}</div>)}</div>}<div className="evidence"><TerminalSquare size={16}/><span><small>Direct evidence</small><code>{issue.evidence}</code></span><em>{issue.confidence} confidence · {issue.confidence_basis}</em></div><div className="action-grid"><div className="recommendation"><Sparkles size={16}/><span><strong>Recommended remediation</strong>{issue.suggested_fix}</span></div><div className="recommendation test"><TestTube2 size={16}/><span><strong>Regression test</strong>{issue.recommended_test}</span></div></div></div></article>)}{!issues.length&&<Blank title="No issues detected"/>}</div></>;
}

function DebugPage({repo,problem,setProblem,run,onRun,busy}:{repo?:Repository;problem:string;setProblem:(v:string)=>void;run:Run|null;onRun:()=>void;busy:boolean}) {
  const result=run?.result;
  return <><div className="page-head"><div><span className="kicker"><Bug size={14}/> Agent workspace</span><h1>Debug Lab</h1><p>Trace a reported failure from symptom to verifiable evidence.</p></div></div>
    <div className="debug-layout"><section className="debug-main"><div className="prompt-box"><div className="prompt-head"><span><Braces size={16}/>{repo?.name||"Select a repository"}</span><small>Investigation brief</small></div><textarea value={problem} onChange={e=>setProblem(e.target.value)} aria-label="Problem description"/><div className="prompt-foot"><span><ShieldCheck size={14}/> Read-only investigation</span><button className="primary" onClick={onRun} disabled={busy||!repo}>{busy?<LoaderCircle className="spin" size={16}/>:<Play size={16}/>} Start investigation</button></div></div>
      {result?.explanation && <ExplanationPanel explanation={result.explanation}/>} 
      {result ? <div className="investigation"><div className="section-label"><span>Execution trace</span><small>{result.history.length} completed steps</small></div>{result.history.map((step:any,i:number)=><div className="agent-step" key={i}><div className="step-rail"><span><Check size={13}/></span>{i<result.history.length-1&&<i/>}</div><div><small>{step.node.replace("_"," ")}</small><strong>{displayPath(step.detail)}</strong></div><span className="step-status">complete</span></div>)}</div> : <div className="debug-placeholder"><div className="radar"><span/><span/><Bug size={24}/></div><h3>Ready to investigate</h3><p>The agent will retrieve symbols, inspect deterministic findings, form a hypothesis, propose a regression test, and report only what can be verified.</p></div>}
    </section>
    <aside className="evidence-panel"><div className="section-label"><span>Evidence board</span></div>{result ? <>
      <Evidence title="Root-cause hypothesis" icon={CircleDot}>{result.hypotheses.map((h:any,i:number)=><div key={i}><span className={`confidence ${h.confidence}`}>{h.confidence}</span><p>{h.claim}</p><code>{displayPath(h.file)}:{h.line}</code></div>)}</Evidence>
      <Evidence title="Observed evidence" icon={Search}>{result.evidence.map((e:string)=><code className="block-code" key={e}>{displayPath(e)}</code>)}</Evidence>
      {result.test_results?.before&&<Evidence title="Before / after proof" icon={TestTube2}><div className="proof-grid"><div><span>Before candidate</span><strong className={result.test_results.before.status}>{result.test_results.before.status}</strong><small>Exit {result.test_results.before.exit_code} · {(result.test_results.before.duration_ms/1000).toFixed(2)}s</small></div><ArrowRight size={15}/><div><span>After candidate</span><strong className={result.test_results.after.status}>{result.test_results.after.status}</strong><small>Exit {result.test_results.after.exit_code} · {(result.test_results.after.duration_ms/1000).toFixed(2)}s</small></div></div><details className="patch-proof"><summary>Candidate patch</summary><code>- {result.test_results.candidate_patch.before}</code><code>+ {result.test_results.candidate_patch.after}</code></details></Evidence>}
      <Evidence title="Verification" icon={ShieldCheck}><div className={`verification ${result.verification.status}`}><strong>{result.verification.status.replaceAll("_"," ")}</strong><p>{result.verification.summary}</p></div></Evidence>
    </> : <div className="muted-box">Evidence and retrieved code will appear here as the investigation progresses.</div>}</aside></div></>;
}

function TestRunsPage({repo,onError}:{repo?:Repository;onError:(message:string)=>void}) {
  const [runs,setRuns]=useState<TestRun[]>([]); const [running,setRunning]=useState(false);
  const isPython=(repo?.profile?.languages||[]).some((item:any)=>item.name==="Python");
  const latest=runs[0];
  const load=()=>repo&&api.testRuns(repo.id).then(setRuns).catch(e=>onError(e.message));
  useEffect(()=>{ void load(); },[repo?.id]);
  async function execute(){if(!repo)return;setRunning(true);try{const run=await api.runTests(repo.id,isPython?"pytest":"npm_test");setRuns(current=>[run,...current]);}catch(e){onError((e as Error).message);}finally{setRunning(false)}}
  return <><div className="page-head"><div><span className="kicker"><TestTube2 size={14}/> Sandboxed execution</span><h1>Test runs</h1><p>Execute the repository's configured test suite under strict resource and network limits.</p></div><button className="primary" onClick={execute} disabled={!repo||running||repo.status!=="ready"}>{running?<LoaderCircle className="spin" size={16}/>:<Play size={16}/>} Run {isPython?"pytest":"npm test"}</button></div>
    <div className="execution-policy"><ShieldCheck size={18}/><div><strong>Isolated by default</strong><p>Network disabled · read-only repository · 1 CPU · 512 MB memory · execution timeout</p></div><span>{repo?.status==="ready"?"Repository ready":"Scan required"}</span></div>
    {latest?.summary&&<><section className="test-metrics"><div><span>Completed</span><strong>{latest.summary.completed_tests}</strong><small>tests reached a result</small></div><div className="success"><span>Passed</span><strong>{latest.summary.passed}</strong><small>assertions successful</small></div><div className="danger"><span>Failed</span><strong>{latest.summary.failed}</strong><small>assertion failures</small></div><div className="warning"><span>Collection errors</span><strong>{latest.summary.errors}</strong><small>suite setup/import errors</small></div></section><section className={`test-diagnosis ${latest.summary.outcome}`}><span className="diagnosis-icon"><AlertTriangle size={19}/></span><div><small>{latest.summary.outcome.replaceAll("_"," ")}</small><h2>{latest.summary.headline}</h2><p>{displayPath(latest.summary.cause)||"The runner completed without an additional diagnostic."}</p><strong>Recommended next step</strong><p>{latest.summary.recommended_action}</p></div></section></>}
    <section className="panel"><PanelTitle title="Execution history" subtitle={`${runs.length} recorded run${runs.length===1?"":"s"}`}/>{runs.length?<div className="run-list">{runs.map(run=><article className="run-row expanded" key={run.id}><span className={`run-state ${run.summary?.outcome||run.status}`}>{run.status==="passed"?<Check size={15}/>:<AlertTriangle size={15}/>}</span><div><strong>Test run #{run.id}</strong><small>{run.summary?.headline||`Process exited with code ${run.exit_code}`} · {(run.duration_ms/1000).toFixed(2)} seconds</small></div><span className={`badge ${run.status==="passed"?"passed":"critical"}`}>{run.summary?.outcome?.replaceAll("_"," ")||run.status}</span>{run.summary&&<div className="run-counts"><span><b>{run.summary.passed}</b> passed</span><span><b>{run.summary.failed}</b> failed</span><span><b>{run.summary.errors}</b> errors</span><span>exit {run.exit_code}</span></div>}<details><summary>View complete runner output</summary><pre>{run.output||run.stdout||run.stderr||"No output captured."}</pre></details></article>)}</div>:<div className="history-empty"><TestTube2 size={28}/><h3>No tests have been executed</h3><p>Start a sandboxed run to capture exit status, duration, and console output.</p></div>}</section></>;
}

function ReportsPage({repo,onError}:{repo?:Repository;onError:(message:string)=>void}) {
  const [reports,setReports]=useState<ReportSummary[]>([]); const [selected,setSelected]=useState<any>(null); const [loading,setLoading]=useState(false);
  useEffect(()=>{if(repo)api.reports(repo.id).then(setReports).catch(e=>onError(e.message));},[repo?.id]);
  async function openReport(id:number){setLoading(true);try{setSelected(await api.report(id));}catch(e){onError((e as Error).message);}finally{setLoading(false)}}
  return <><div className="page-head"><div><span className="kicker"><BookOpen size={14}/> Engineering record</span><h1>Reports</h1><p>Persisted findings, investigations, and verification status for {repo?.name||"the selected repository"}.</p></div></div>
    <div className="reports-layout"><section className="panel report-index"><PanelTitle title="Available reports" subtitle={`${reports.length} saved artifact${reports.length===1?"":"s"}`}/>{reports.length?<div className="report-list">{reports.map(report=><button className={selected?.id===report.id?"report-row selected":"report-row"} onClick={()=>openReport(report.id)} key={report.id}><span className="report-icon">{report.kind==="debug"?<Bug size={16}/>:<ShieldCheck size={16}/>}</span><div><strong>{report.kind==="debug"?"Debug investigation":"Code analysis"} #{report.id}</strong><small>{new Date(report.created_at).toLocaleString()} · {report.finding_count} findings</small></div><ChevronRight size={15}/></button>)}</div>:<div className="history-empty"><BookOpen size={28}/><h3>No reports yet</h3><p>Run a code analysis or debugging investigation to create one.</p></div>}</section>
      <section className="panel report-detail">{loading?<div className="history-empty"><LoaderCircle className="spin" size={28}/><p>Loading report…</p></div>:selected?<ReportDetail report={selected}/>:<div className="history-empty"><BookOpen size={28}/><h3>Select a report</h3><p>Observed facts, hypotheses, and verification evidence will appear here.</p></div>}</section></div></>;
}

function ReportDetail({report}:{report:any}) { const result=report.result||{}; return <div className="report-content"><div className="report-heading"><span>{report.kind}</span><h2>Engineering report #{report.id}</h2><p>{report.repository?.project_name||"Repository"}</p></div><div className="report-facts"><div><span>Observed facts</span><strong>{Array.isArray(report.observed_facts)?report.observed_facts.length:0}</strong></div><div><span>Hypotheses</span><strong>{report.ai_hypotheses?.length||0}</strong></div><div><span>Verification</span><strong>{report.verification?.status?.replaceAll("_"," ")||"not applicable"}</strong></div></div>{result.explanation&&<><h3>Root-cause explanation</h3><p>{result.explanation.plain_language}</p><div className="report-callout"><strong>Why it happens</strong><p>{result.explanation.why_it_happens}</p></div></>}{result.summary&&<><h3>Analysis summary</h3><p>{result.summary.executive_summary}</p></>}<h3>Evidence</h3><pre>{JSON.stringify(report.observed_facts,null,2)}</pre></div> }

function Evidence({title,icon:Icon,children}:{title:string;icon:any;children:React.ReactNode}) { return <div className="evidence-card"><h4><Icon size={15}/>{title}</h4>{children}</div> }
function Blank({title}:{title:string}) { return <div className="blank"><FileCode2 size={24}/><p>{title}</p></div> }

function ExplanationPanel({explanation}:{explanation:any}) {
  const location = explanation.location;
  return <section className="explanation-panel">
    <div className="explanation-head"><div><span className="finding-label"><AlertTriangle size={14}/> Root-cause explanation</span><h2>{explanation.headline}</h2></div><span className={`confidence-pill ${explanation.confidence}`}>{explanation.confidence} confidence</span></div>
    <p className="plain-language">{explanation.plain_language}</p>
    {location && <div className="location-chip"><FileCode2 size={14}/><code>{displayPath(location.file)}:{location.line}</code></div>}
    <div className="explanation-grid">
      <div><span>Why it happens</span><p>{explanation.why_it_happens}</p></div>
      <div><span>User impact</span><p>{explanation.impact}</p></div>
      <div><span>Recommended correction</span><p>{explanation.recommended_fix || explanation.next_action}</p></div>
      <div><span>Regression test must prove</span><p>{explanation.test_intent || "The reported failure is handled predictably."}</p></div>
    </div>
    {!!explanation.code_excerpt?.length && <div className="source-excerpt"><div className="source-title"><Code2 size={14}/><span>Relevant source</span><code>{displayPath(location?.file)}</code></div>{explanation.code_excerpt.map((line:any)=><div className={line.highlighted?"source-line highlighted":"source-line"} key={line.line}><span>{line.line}</span><code>{line.text || " "}</code>{line.highlighted&&<i>problematic line</i>}</div>)}</div>}
    <div className="reasoning-boundary"><div><strong>Observed fact</strong><p>{explanation.fact_vs_inference?.observed || explanation.observed_behavior}</p></div><ArrowRight size={16}/><div><strong>Engineering inference</strong><p>{explanation.fact_vs_inference?.inference || explanation.why_it_happens}</p></div></div>
    <div className="confidence-reason"><ShieldCheck size={15}/><span><strong>Why this confidence?</strong>{explanation.confidence_reason}</span></div>
  </section>;
}

function displayPath(value: string | undefined): string {
  if (!value) return "unknown";
  return value.replace(/\\/g, "/").replace(/\S*?(?:\.repowise\/)?workspaces\/\d+\//g, "");
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App/></React.StrictMode>);
