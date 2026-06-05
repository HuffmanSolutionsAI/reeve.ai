import React, { useEffect, useMemo, useState } from 'react';
import {
  MessageSquare, Building2, ListChecks, ScrollText,
  Send, ArrowUpRight, Sparkles,
} from 'lucide-react';
import ArtifactCard from './components/ArtifactCard.jsx';
import * as api from './api.js';
import { streamChat } from './sse.js';

const INVESTOR_ID = import.meta.env.VITE_INVESTOR_ID || 'dev-investor';
const POLL_MS = 8000;

const NAV = [
  { key: 'chat', label: 'Reeve', icon: MessageSquare },
  { key: 'pipeline', label: 'Pipeline', icon: ListChecks },
  { key: 'portfolio', label: 'Portfolio', icon: Building2 },
  { key: 'activity', label: 'Activity', icon: ScrollText },
];

const TEAM = {
  Acquisition: ['Sam', 'Ana', 'Cole'],
  'Asset Mgmt': ['Cara', 'Manny', 'Leo'],
  'Finance & Tax': ['Bea', 'Reed', 'Tess'],
};

const AGENT_COLOR = {
  ana: 'var(--green-2)', sam: 'var(--brass)', cole: '#5a7d8c',
  cara: 'var(--clay)', manny: '#7a5a8c', leo: '#8c7a5a',
  bea: '#5a7d8c', reed: '#5a7d8c', tess: '#8c5a7a',
  reeve: 'var(--ink)', investor: 'var(--ink-soft)',
};

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

function AgentChip({ id, name }) {
  const initial = (name || id || '?').slice(0, 1).toUpperCase();
  return (
    <div className="agent-av" style={{ background: AGENT_COLOR[id] || '#888' }}>{initial}</div>
  );
}

function Rail({ view, setView, investor, portfolio }) {
  return (
    <aside className="rail">
      <div className="brand"><Seal /><span className="wordmark">Reeve</span></div>
      <nav className="nav">
        {NAV.map(n => (
          <button key={n.key} className={`nav-item ${view === n.key ? 'on' : ''}`} onClick={() => setView(n.key)}>
            <n.icon size={17} strokeWidth={1.75} />
            <span>{n.label}</span>
          </button>
        ))}
      </nav>
      <div className="team">
        <div className="team-head">Your team</div>
        {Object.entries(TEAM).map(([desk, members]) => (
          <div key={desk} className="desk">
            <div className="desk-name">{desk}</div>
            <div className="desk-members">{members.join('  ·  ')}</div>
          </div>
        ))}
      </div>
      {investor && (
        <div className="user">
          <div className="avatar">{(investor.name || '?').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()}</div>
          <div className="user-meta">
            <div className="user-name">{investor.name}</div>
            <div className="user-sub">{investor.entity_name || '—'}</div>
          </div>
        </div>
      )}
    </aside>
  );
}

function MessageBubble({ m }) {
  if (m.speaker === 'investor') {
    return (
      <div className="msg user-msg fade">
        <div className="bubble">{m.text}</div>
      </div>
    );
  }
  const avatar = m.speaker === 'reeve' ? <Seal size={26} /> : <AgentChip id={m.speaker} name={m.name} />;
  return (
    <div className="msg fade">
      {avatar}
      <div className="msg-body">
        <div className="speaker">{m.name || m.speaker}{m.role_label && <span className="speaker-role">{m.role_label}</span>}</div>
        {m.handoffs?.map((h, i) => (
          <div key={i} className="handoff"><ArrowUpRight size={13} strokeWidth={2} />{h.name || h.agent} · {h.desk}</div>
        ))}
        {m.text && <p>{m.text}</p>}
        {m.artifact && <ArtifactCard payload={m.artifact} />}
        {m.working && <div className="working">{m.working}…</div>}
      </div>
    </div>
  );
}

function ChatView({ messages, streaming, streamAgent, draft, setDraft, send, investor, portfolio }) {
  const ctxTitle = portfolio?.portfolios?.[0]?.name || (investor ? `${investor.name}'s holdings` : 'Reeve');
  const ctxSub = portfolio?.totals ? `${portfolio.totals.units || 0} units · ${portfolio.totals.buildings || 0} buildings` : '—';
  return (
    <main className="chat">
      <header className="chat-head">
        <div>
          <div className="ctx-title">{ctxTitle}</div>
          <div className="ctx-sub">{ctxSub}</div>
        </div>
        <div className="status">
          <span className="dot" style={{ background: streaming ? 'var(--clay)' : 'var(--green-2)' }} />
          {streaming ? `${streamAgent || 'Reeve'} working…` : 'Reeve is on'}
        </div>
      </header>

      <div className="thread">
        {messages.length === 0 && (
          <div className="empty">Ask Reeve anything — a listing, an invoice, a tenant, your cash flow…</div>
        )}
        {messages.map((m, i) => <MessageBubble key={i} m={m} />)}
      </div>

      <div className="composer">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder="Ask Reeve anything — a listing, an invoice, a tenant, your cash flow…"
          disabled={streaming}
        />
        <button className="send" onClick={send} disabled={streaming || !draft.trim()}>
          <Send size={16} strokeWidth={2} />
        </button>
      </div>
    </main>
  );
}

function PipelineView({ pipeline }) {
  const order = ['sourced', 'analyzed', 'pursue', 'pass', 'under_contract', 'closed'];
  return (
    <main className="chat" style={{ padding: '24px 28px', overflowY: 'auto' }}>
      <h2 style={{ fontFamily: 'Fraunces, serif', marginBottom: 18 }}>Pipeline</h2>
      <div className="pipeline-grid">
        {order.map(status => {
          const items = pipeline?.by_status?.[status] || [];
          return (
            <div key={status} className="pipe-col">
              <div className="pipe-head">{status.replace('_', ' ')} <span className="pipe-count">{items.length}</span></div>
              {items.map(d => (
                <div key={d._id} className="pipe-card">
                  <div className="pipe-addr">{d.address}</div>
                  <div className="pipe-meta">{d.units || '?'} units · ${(d.ask || 0).toLocaleString()}</div>
                </div>
              ))}
              {items.length === 0 && <div className="pipe-empty">—</div>}
            </div>
          );
        })}
      </div>
    </main>
  );
}

function PortfolioView({ portfolio }) {
  return (
    <main className="chat" style={{ padding: '24px 28px', overflowY: 'auto' }}>
      <h2 style={{ fontFamily: 'Fraunces, serif', marginBottom: 18 }}>Portfolio</h2>
      {(portfolio?.portfolios || []).map(p => (
        <div key={p._id} className="portfolio-block">
          <div className="portfolio-name">{p.name}</div>
          {(p.buildings || []).map(b => (
            <div key={b._id} className="building">
              <div className="building-head">{b.address} <span className="building-meta">{b.units_count} units</span></div>
              <div className="units-grid">
                {(b.units || []).map(u => (
                  <div key={u._id} className={`unit-chip ${u.status}`}>{u.label} · {u.status}</div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ))}
      {(!portfolio?.portfolios || portfolio.portfolios.length === 0) && (
        <div className="empty">No portfolios yet. Seed one to see it here.</div>
      )}
    </main>
  );
}

function ActivityRail({ events }) {
  return (
    <aside className="activity">
      <div className="act-head">
        <span>Activity</span><span className="act-link">Audit log</span>
      </div>
      <div className="act-list">
        {events.length === 0 && <div className="empty">No activity yet.</div>}
        {events.map((e, i) => (
          <div key={i} className="act-item">
            <div className="act-chip" style={{ background: AGENT_COLOR[e.actor] || '#888' }}>
              {(e.actor || '?').slice(0, 1).toUpperCase()}
            </div>
            <div>
              <div className="act-text">
                <strong>{e.actor}</strong> {e.kind}
                {e.detail?.tool && <> · <code>{e.detail.tool}</code></>}
                {e.detail?.type && <> · {e.detail.type}</>}
              </div>
              <div className="act-meta">{new Date(e.ts).toLocaleString()}</div>
            </div>
          </div>
        ))}
      </div>
      <div className="act-foot">
        <Sparkles size={13} strokeWidth={1.75} />
        Every action Reeve takes is logged here.
      </div>
    </aside>
  );
}

export default function App() {
  const [view, setView] = useState('chat');
  const [investor, setInvestor] = useState(null);
  const [convId, setConvId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [activity, setActivity] = useState([]);
  const [pipeline, setPipeline] = useState({ by_status: {}, counts: {} });
  const [portfolio, setPortfolio] = useState({ portfolios: [], totals: {} });
  const [draft, setDraft] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamAgent, setStreamAgent] = useState(null);

  const refreshActivity = () =>
    api.fetchActivity(INVESTOR_ID).then(r => setActivity(r.events)).catch(() => {});
  const refreshPipeline = () =>
    api.fetchPipeline(INVESTOR_ID).then(setPipeline).catch(() => {});
  const refreshPortfolio = () =>
    api.fetchPortfolio(INVESTOR_ID).then(setPortfolio).catch(() => {});

  useEffect(() => {
    api.fetchInvestor(INVESTOR_ID).then(setInvestor).catch(() => {});
    refreshActivity();
    refreshPipeline();
    refreshPortfolio();
    const t = setInterval(refreshActivity, POLL_MS);
    return () => clearInterval(t);
  }, []);

  const send = async () => {
    if (!draft.trim() || streaming) return;
    const userText = draft;
    setDraft('');
    setStreaming(true);
    setStreamAgent('reeve');

    setMessages(prev => [
      ...prev,
      { speaker: 'investor', text: userText },
      { speaker: 'reeve', name: 'Reeve', text: '', handoffs: [], artifact: null, working: 'Routing' },
    ]);

    const updateLast = (mutator) => setMessages(prev => {
      const m = [...prev];
      m[m.length - 1] = { ...m[m.length - 1], ...mutator(m[m.length - 1]) };
      return m;
    });

    try {
      await streamChat(
        { investor_id: INVESTOR_ID, message: userText, conversation_id: convId },
        {
          conversation: ({ id }) => setConvId(id),
          routing: ({ agent, name }) => { setStreamAgent(name || agent); updateLast(() => ({ working: `${name || agent} thinking` })); },
          handoff: ({ agent, name, desk }) => updateLast(p => ({ handoffs: [...(p.handoffs || []), { agent, name, desk }], working: `${name || agent} working` })),
          tool: ({ agent, tool }) => updateLast(() => ({ working: `${tool}` })),
          artifact: ({ payload }) => updateLast(() => ({ artifact: payload, working: null })),
          message: ({ agent, name, text }) => updateLast(() => ({ speaker: agent, name: name || agent, text, working: null })),
          proposal: ({ summary }) => updateLast(p => ({ text: (p.text || '') + `\n[Proposal queued: ${summary}]` })),
          error: ({ message }) => updateLast(() => ({ text: `Error: ${message}`, working: null })),
        },
      );
    } finally {
      setStreaming(false);
      setStreamAgent(null);
      refreshActivity();
      refreshPipeline();
      refreshPortfolio();
    }
  };

  return (
    <div className="reeve-root">
      <Rail view={view} setView={setView} investor={investor} portfolio={portfolio} />
      {view === 'chat' && (
        <ChatView
          messages={messages} streaming={streaming} streamAgent={streamAgent}
          draft={draft} setDraft={setDraft} send={send}
          investor={investor} portfolio={portfolio}
        />
      )}
      {view === 'pipeline' && <PipelineView pipeline={pipeline} />}
      {view === 'portfolio' && <PortfolioView portfolio={portfolio} />}
      {view === 'activity' && (
        <main className="chat" style={{ padding: '24px 28px', overflowY: 'auto' }}>
          <h2 style={{ fontFamily: 'Fraunces, serif', marginBottom: 18 }}>Activity</h2>
          {activity.map((e, i) => (
            <div key={i} className="act-row">
              <div className="act-chip" style={{ background: AGENT_COLOR[e.actor] || '#888' }}>
                {(e.actor || '?').slice(0, 1).toUpperCase()}
              </div>
              <div>
                <div><strong>{e.actor}</strong> {e.kind} {e.detail?.tool && <code>· {e.detail.tool}</code>}</div>
                <div className="act-meta">{new Date(e.ts).toLocaleString()}</div>
              </div>
            </div>
          ))}
        </main>
      )}
      <ActivityRail events={activity} />
    </div>
  );
}
