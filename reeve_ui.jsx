import React, { useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Cell, Tooltip,
} from "recharts";
import {
  MessageSquare, Building2, ListChecks, ScrollText, Send,
  ArrowUpRight, Sparkles,
} from "lucide-react";
 
/* ------------------------------------------------------------------ */
/*  Reeve — workspace mockup. Single screen: chat-as-command-surface,  */
/*  visible multi-agent team, an inline deal-analysis artifact, and    */
/*  an activity/audit rail. Brand: estate-steward / refined heritage.  */
/* ------------------------------------------------------------------ */
 
const rentData = [
  { u: "1A", inplace: 1150, market: 1450 },
  { u: "1B", inplace: 1100, market: 1425 },
  { u: "2A", inplace: 1295, market: 1450 },
  { u: "2B", inplace: 1200, market: 1425 },
  { u: "3A", inplace: 1395, market: 1500 },
  { u: "3B", inplace: 1150, market: 1475 },
  { u: "4A", inplace: 1250, market: 1500 },
  { u: "4B", inplace: 1325, market: 1500 },
];
 
const team = {
  Acquisition: ["Sam", "Ana", "Cole"],
  "Asset Mgmt": ["Cara", "Manny", "Leo"],
  "Finance & Tax": ["Bea", "Reed", "Tess"],
};
 
const nav = [
  { icon: MessageSquare, label: "Reeve", active: true },
  { icon: ListChecks, label: "Pipeline" },
  { icon: Building2, label: "Portfolio" },
  { icon: ScrollText, label: "Activity" },
];
 
const activity = [
  { who: "Ana", color: "var(--green-2)", t: "just now", text: "Underwrote 1423 Elmwood Ave — pursue at \u2264 $1.06M." },
  { who: "Sam", color: "var(--brass)", t: "9:12 AM", text: "Surfaced 3 new candidates from the distressed pipeline." },
  { who: "Bea", color: "#5a7d8c", t: "Yesterday", text: "Reconciled March transactions — 2 flagged for your review." },
  { who: "Reed", color: "#5a7d8c", t: "Yesterday", text: "Portfolio cash flow report ready for April." },
  { who: "Cara", color: "var(--clay)", t: "Mon", text: "Drafted renewal note for Unit 2B \u2014 awaiting your sign-off." },
];
 
const Metric = ({ label, value, sub, accent }) => (
  <div className="metric">
    <div className="metric-label">{label}</div>
    <div className="metric-value" style={accent ? { color: "var(--green-2)" } : undefined}>{value}</div>
    {sub && <div className="metric-sub">{sub}</div>}
  </div>
);
 
function Seal({ size = 30 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none">
      <circle cx="20" cy="20" r="18.5" stroke="var(--brass)" strokeWidth="1.4" />
      <circle cx="20" cy="20" r="15" fill="var(--ink)" />
      <text x="20" y="27.5" textAnchor="middle" fontFamily="Fraunces, serif"
        fontSize="20" fontWeight="600" fill="var(--paper)">R</text>
    </svg>
  );
}
 
export default function App() {
  const [draft, setDraft] = useState("");
 
  return (
    <div className="reeve-root">
      <style>{css}</style>
 
      {/* ---------------- LEFT RAIL ---------------- */}
      <aside className="rail">
        <div className="brand">
          <Seal />
          <span className="wordmark">Reeve</span>
        </div>
 
        <nav className="nav">
          {nav.map((n) => (
            <button key={n.label} className={`nav-item ${n.active ? "on" : ""}`}>
              <n.icon size={17} strokeWidth={1.75} />
              <span>{n.label}</span>
            </button>
          ))}
        </nav>
 
        <div className="team">
          <div className="team-head">Your team</div>
          {Object.entries(team).map(([desk, members]) => (
            <div key={desk} className="desk">
              <div className="desk-name">{desk}</div>
              <div className="desk-members">{members.join("  ·  ")}</div>
            </div>
          ))}
        </div>
 
        <div className="user">
          <div className="avatar">JM</div>
          <div className="user-meta">
            <div className="user-name">James M.</div>
            <div className="user-sub">Oakwood Holdings</div>
          </div>
        </div>
      </aside>
 
      {/* ---------------- CENTER: CHAT ---------------- */}
      <main className="chat">
        <header className="chat-head">
          <div>
            <div className="ctx-title">Oakwood Portfolio</div>
            <div className="ctx-sub">47 units · 6 buildings</div>
          </div>
          <div className="status"><span className="dot" />Reeve is on</div>
        </header>
 
        <div className="thread">
          <div className="msg user-msg fade" style={{ animationDelay: ".05s" }}>
            <div className="bubble">
              Take a look at 1423 Elmwood Ave — 8-unit, asking $1.15M. Worth a closer look?
            </div>
          </div>
 
          <div className="msg fade" style={{ animationDelay: ".18s" }}>
            <Seal size={26} />
            <div className="msg-body">
              <div className="speaker">Reeve</div>
              <p>On it. Pulling the listing and comps now — handing the numbers to Ana.</p>
              <div className="handoff"><ArrowUpRight size={13} strokeWidth={2} />Ana · Underwriting</div>
            </div>
          </div>
 
          <div className="msg fade" style={{ animationDelay: ".34s" }}>
            <div className="agent-av" style={{ background: "var(--green-2)" }}>A</div>
            <div className="msg-body">
              <div className="speaker">Ana <span className="speaker-role">Underwriting</span></div>
 
              {/* -------- DEAL ANALYSIS ARTIFACT -------- */}
              <div className="card">
                <div className="card-top">
                  <div>
                    <div className="card-title">1423 Elmwood Ave</div>
                    <div className="card-meta">8 units · Asking $1,150,000 · $143,750 / unit</div>
                  </div>
                  <div className="verdict">Pursue at ≤ $1.06M</div>
                </div>
 
                <div className="metrics">
                  <Metric label="Cap (in-place)" value="5.4%" sub="pro-forma 6.9%" />
                  <Metric label="Cash-on-cash" value="4.1%" sub="stab. 8.7%" accent />
                  <Metric label="DSCR" value="1.24×" sub="yr 1" />
                  <Metric label="Avg rent" value="$1,233" sub="market $1,466" />
                  <Metric label="Rent upside" value="+19%" sub="$1,866 / mo" accent />
                </div>
 
                <div className="chart-wrap">
                  <div className="chart-label">In-place rent vs. market — by unit</div>
                  <ResponsiveContainer width="100%" height={148}>
                    <BarChart data={rentData} barGap={3} margin={{ top: 4, right: 4, left: -18, bottom: 0 }}>
                      <XAxis dataKey="u" tick={{ fontSize: 10, fill: "var(--ink-soft)", fontFamily: "IBM Plex Mono" }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fontSize: 10, fill: "var(--ink-soft)", fontFamily: "IBM Plex Mono" }} axisLine={false} tickLine={false} />
                      <Tooltip cursor={{ fill: "rgba(0,0,0,.04)" }}
                        contentStyle={{ fontFamily: "IBM Plex Mono", fontSize: 11, border: "1px solid var(--line)", borderRadius: 6, background: "var(--paper)" }} />
                      <Bar dataKey="inplace" radius={[2, 2, 0, 0]}>
                        {rentData.map((_, i) => <Cell key={i} fill="#C9BFA6" />)}
                      </Bar>
                      <Bar dataKey="market" radius={[2, 2, 0, 0]}>
                        {rentData.map((_, i) => <Cell key={i} fill="var(--green)" />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
 
                <div className="assumptions">
                  <span>Vacancy 5%</span><span>Mgmt 8%</span><span>Taxes reassessed at sale</span>
                  <span>CapEx $300/unit/yr</span><span>6.75% · 25yr · 70% LTV</span>
                </div>
 
                <p className="card-note">
                  The thesis is the rent gap — eight units running 19% under market. The upside is real;
                  the in-place yield doesn't clear your 7% floor at full ask. Works at ~$1.06M.
                </p>
              </div>
            </div>
          </div>
 
          <div className="msg fade" style={{ animationDelay: ".5s" }}>
            <Seal size={26} />
            <div className="msg-body">
              <div className="speaker">Reeve</div>
              <p>
                Net: a good building at the wrong price. I'd anchor low. Want me to have Cole draft an LOI
                at $1.06M? That one needs your sign-off before anything leaves the building.
              </p>
            </div>
          </div>
        </div>
 
        <div className="composer">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask Reeve anything — a listing, an invoice, a tenant, your cash flow…"
          />
          <button className="send"><Send size={16} strokeWidth={2} /></button>
        </div>
      </main>
 
      {/* ---------------- RIGHT RAIL: ACTIVITY ---------------- */}
      <aside className="activity">
        <div className="act-head">
          <span>Activity</span>
          <span className="act-link">Audit log</span>
        </div>
        <div className="act-list">
          {activity.map((a, i) => (
            <div key={i} className="act-item">
              <div className="act-chip" style={{ background: a.color }}>{a.who[0]}</div>
              <div>
                <div className="act-text">{a.text}</div>
                <div className="act-meta">{a.who} · {a.t}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="act-foot">
          <Sparkles size={13} strokeWidth={1.75} />
          Every action Reeve takes is logged here.
        </div>
      </aside>
    </div>
  );
}
 
const css = `
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Hanken+Grotesk:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
 
:root{
  --paper:#FBF8F1; --paper-2:#F4EFE4; --ink:#1C1B17; --ink-soft:#6B675C;
  --line:#E4DDCD; --green:#1E4233; --green-2:#2F6B4F; --brass:#A9854A; --clay:#9B4A38;
}
*{box-sizing:border-box;margin:0;padding:0}
.reeve-root{
  display:grid; grid-template-columns:230px 1fr 312px; height:100vh; min-height:640px;
  background:var(--paper); color:var(--ink);
  font-family:'Hanken Grotesk',system-ui,sans-serif; font-size:14px; line-height:1.5;
  -webkit-font-smoothing:antialiased;
}
@keyframes fade{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.fade{animation:fade .55s cubic-bezier(.2,.7,.2,1) both}
 
/* ---- LEFT RAIL ---- */
.rail{
  background:var(--ink); color:#E8E2D4; display:flex; flex-direction:column;
  padding:22px 18px; gap:26px;
}
.brand{display:flex; align-items:center; gap:10px}
.wordmark{font-family:'Fraunces',serif; font-size:25px; font-weight:600; letter-spacing:.2px; color:var(--paper)}
.nav{display:flex; flex-direction:column; gap:3px}
.nav-item{
  display:flex; align-items:center; gap:11px; padding:9px 11px; border-radius:8px;
  background:none; border:none; color:#A7A192; font:inherit; font-size:13.5px; cursor:pointer;
  text-align:left; transition:.15s;
}
.nav-item:hover{background:rgba(255,255,255,.05); color:#E8E2D4}
.nav-item.on{background:rgba(47,107,79,.22); color:#EAF3EC; box-shadow:inset 2px 0 0 var(--green-2)}
.team{margin-top:auto; display:flex; flex-direction:column; gap:13px}
.team-head{font-size:10.5px; text-transform:uppercase; letter-spacing:1.4px; color:#76705f}
.desk-name{font-size:10px; text-transform:uppercase; letter-spacing:1px; color:var(--brass); margin-bottom:2px}
.desk-members{font-family:'IBM Plex Mono',monospace; font-size:12px; color:#BDB7A6}
.desk{padding-left:1px}
.user{display:flex; align-items:center; gap:10px; padding-top:16px; border-top:1px solid rgba(255,255,255,.08)}
.avatar{width:30px; height:30px; border-radius:50%; background:var(--brass); color:var(--ink);
  display:grid; place-items:center; font-weight:600; font-size:12px}
.user-name{font-size:13px; color:#E8E2D4} .user-sub{font-size:11px; color:#86806f}
 
/* ---- CENTER ---- */
.chat{display:flex; flex-direction:column; overflow:hidden; border-right:1px solid var(--line)}
.chat-head{
  display:flex; justify-content:space-between; align-items:center;
  padding:17px 28px; border-bottom:1px solid var(--line); background:var(--paper)
}
.ctx-title{font-family:'Fraunces',serif; font-size:17px; font-weight:600}
.ctx-sub{font-family:'IBM Plex Mono',monospace; font-size:11.5px; color:var(--ink-soft); margin-top:1px}
.status{display:flex; align-items:center; gap:7px; font-size:12px; color:var(--ink-soft)}
.dot{width:7px; height:7px; border-radius:50%; background:var(--green-2); box-shadow:0 0 0 3px rgba(47,107,79,.18)}
.thread{flex:1; overflow-y:auto; padding:26px 28px; display:flex; flex-direction:column; gap:20px}
.msg{display:flex; gap:12px; max-width:680px}
.msg-body{padding-top:1px}
.speaker{font-family:'Fraunces',serif; font-size:14px; font-weight:600; margin-bottom:3px}
.speaker-role{font-family:'Hanken Grotesk'; font-size:11px; font-weight:500; color:var(--ink-soft); margin-left:6px}
.msg p{font-size:14px; color:#2c2a24}
.user-msg{align-self:flex-end}
.user-msg .bubble{background:var(--ink); color:#F2EEE3; padding:11px 15px; border-radius:14px 14px 4px 14px; font-size:13.5px}
.agent-av{width:26px; height:26px; border-radius:50%; color:#fff; display:grid; place-items:center;
  font-weight:600; font-size:12px; flex-shrink:0}
.handoff{display:inline-flex; align-items:center; gap:5px; margin-top:8px; padding:4px 10px;
  background:var(--paper-2); border:1px solid var(--line); border-radius:20px;
  font-size:11.5px; font-weight:500; color:var(--green)}
 
/* ---- DEAL CARD ---- */
.card{margin-top:9px; background:var(--paper-2); border:1px solid var(--line); border-radius:14px;
  padding:18px; box-shadow:0 1px 0 rgba(0,0,0,.02); border-top:2px solid var(--green)}
.card-top{display:flex; justify-content:space-between; align-items:flex-start; gap:14px}
.card-title{font-family:'Fraunces',serif; font-size:18px; font-weight:600}
.card-meta{font-family:'IBM Plex Mono',monospace; font-size:11.5px; color:var(--ink-soft); margin-top:3px}
.verdict{background:var(--green); color:#EAF3EC; padding:6px 12px; border-radius:8px;
  font-size:12px; font-weight:600; white-space:nowrap}
.metrics{display:grid; grid-template-columns:repeat(5,1fr); gap:14px; margin:18px 0 6px;
  padding:14px 0; border-top:1px solid var(--line); border-bottom:1px solid var(--line)}
.metric-label{font-size:10.5px; text-transform:uppercase; letter-spacing:.6px; color:var(--ink-soft)}
.metric-value{font-family:'IBM Plex Mono',monospace; font-size:18px; font-weight:500; margin-top:4px}
.metric-sub{font-family:'IBM Plex Mono',monospace; font-size:10.5px; color:var(--ink-soft); margin-top:1px}
.chart-wrap{margin:14px 0 4px}
.chart-label{font-size:11px; color:var(--ink-soft); margin-bottom:6px}
.assumptions{display:flex; flex-wrap:wrap; gap:6px; margin:12px 0}
.assumptions span{font-family:'IBM Plex Mono',monospace; font-size:10.5px; color:var(--ink-soft);
  background:var(--paper); border:1px solid var(--line); padding:3px 8px; border-radius:5px}
.card-note{font-size:13px; color:#2c2a24; line-height:1.55; margin-top:4px}
 
/* ---- COMPOSER ---- */
.composer{display:flex; gap:10px; padding:16px 28px 22px; border-top:1px solid var(--line); background:var(--paper)}
.composer input{flex:1; padding:13px 16px; border:1px solid var(--line); border-radius:12px;
  background:var(--paper-2); font:inherit; font-size:13.5px; color:var(--ink); outline:none}
.composer input:focus{border-color:var(--green-2); box-shadow:0 0 0 3px rgba(47,107,79,.12)}
.composer input::placeholder{color:#9a9484}
.send{width:46px; border:none; border-radius:12px; background:var(--green); color:#EAF3EC;
  display:grid; place-items:center; cursor:pointer; transition:.15s}
.send:hover{background:var(--green-2)}
 
/* ---- RIGHT RAIL ---- */
.activity{background:var(--paper-2); display:flex; flex-direction:column; padding:20px 18px}
.act-head{display:flex; justify-content:space-between; align-items:baseline; margin-bottom:16px}
.act-head>span:first-child{font-family:'Fraunces',serif; font-size:16px; font-weight:600}
.act-link{font-size:11.5px; color:var(--green-2); cursor:pointer; font-weight:500}
.act-list{display:flex; flex-direction:column; gap:3px; overflow-y:auto}
.act-item{display:flex; gap:11px; padding:11px 9px; border-radius:9px; transition:.15s}
.act-item:hover{background:var(--paper)}
.act-chip{width:24px; height:24px; border-radius:50%; color:#fff; display:grid; place-items:center;
  font-size:11px; font-weight:600; flex-shrink:0; margin-top:1px}
.act-text{font-size:12.5px; color:#2c2a24; line-height:1.45}
.act-meta{font-family:'IBM Plex Mono',monospace; font-size:10.5px; color:var(--ink-soft); margin-top:3px}
.act-foot{margin-top:auto; display:flex; align-items:center; gap:8px; padding-top:14px;
  border-top:1px solid var(--line); font-size:11.5px; color:var(--ink-soft)}
`;
