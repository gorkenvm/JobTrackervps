import React, { useState, useEffect } from 'react';
import {
    MapPin, ExternalLink, Trash2, Edit2, Check, X,
    Languages, FileText, Copy, CheckCheck, Download,
    Mail, User, Wand2, Info, ChevronDown
} from 'lucide-react';
import {
    updateJobStatus, updateJobDetails, generateLetter,
    deleteJob, exportLetter, exportCV, generateCVSummary, recompileCV
} from '../services/api';
import { AI_MODELS } from '../utils/aiModels';
import { useLanguage } from '../contexts/LanguageContext';

const STATUS_STYLES = {
    'Yeni':       'bg-emerald-50 text-emerald-700 border-emerald-200',
    'Başvuruldu': 'bg-blue-50 text-blue-700 border-blue-200',
    'Mülakat':    'bg-purple-50 text-purple-700 border-purple-200',
    'Reddedildi': 'bg-red-50 text-red-700 border-red-200',
};

function ScoreRing({ score }) {
    const r = 38;
    const circ = 2 * Math.PI * r;
    const filled = score != null ? (score / 100) * circ : 0;
    const color = score >= 80 ? '#10b981' : score >= 50 ? '#f59e0b' : '#94a3b8';
    return (
        <div className="relative w-28 h-28 shrink-0">
            <svg className="w-28 h-28 -rotate-90" viewBox="0 0 96 96">
                <circle cx="48" cy="48" r={r} fill="none" stroke="#f1f5f9" strokeWidth="9" />
                <circle cx="48" cy="48" r={r} fill="none" stroke={color} strokeWidth="9"
                    strokeDasharray={circ} strokeDashoffset={circ - filled} strokeLinecap="round" />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-2xl font-black text-slate-800 leading-none">{score ?? '—'}</span>
                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider mt-0.5">MATCH</span>
            </div>
        </div>
    );
}

function renderSummary(text) {
    if (!text) return null;
    const sectionRe = /(\[[^\]]+\]:)/g;
    const parts = text.split(sectionRe).filter(p => p.trim());
    const sections = [];
    for (let i = 0; i < parts.length; i++) {
        if (/^\[[^\]]+\]:$/.test(parts[i])) {
            const label = parts[i].replace(/^\[|\]:$/g, '');
            const content = parts[i + 1] ? parts[i + 1].replace(/^\s*\n*/, '').trim() : '';
            sections.push({ label, content });
            i++;
        } else if (!sections.length && parts[i].trim()) {
            sections.push({ label: null, content: parts[i].trim() });
        }
    }
    if (!sections.length) return <p className="text-sm text-slate-600 leading-relaxed">{text}</p>;
    return sections.map((s, i) => (
        <div key={i}>
            {s.label && <span className="text-[10px] font-extrabold text-indigo-500 uppercase tracking-wider">{s.label}</span>}
            <p className="text-sm text-slate-600 leading-snug mt-0.5">{s.content}</p>
        </div>
    ));
}

const BREAKDOWN_KEYS = [
    { key: 'technical', label: 'Technical Stack Match' },
    { key: 'seniority',  label: 'Seniority & Experience' },
    { key: 'industry',   label: 'Industry / Domain Fit' },
    { key: 'education',  label: 'Education & Languages' },
];

function ScoreBreakdown({ breakdownJson }) {
    if (!breakdownJson) return null;
    let bd;
    try { bd = JSON.parse(breakdownJson); } catch { return null; }
    if (!bd || typeof bd !== 'object') return null;
    return (
        <div className="bg-slate-50 border border-slate-100 rounded-xl p-3">
            <p className="text-[10px] font-extrabold text-slate-500 uppercase tracking-wider mb-2.5">Score Breakdown</p>
            <div className="space-y-2.5">
                {BREAKDOWN_KEYS.map(({ key, label }) => {
                    const item = bd[key];
                    if (!item) return null;
                    const { score, max, note } = item;
                    const pct = max > 0 ? (score / max) * 100 : 0;
                    const barColor = pct >= 75 ? 'bg-emerald-500' : pct >= 45 ? 'bg-amber-500' : 'bg-red-400';
                    return (
                        <div key={key}>
                            <div className="flex items-center justify-between mb-1">
                                <span className="text-[11px] font-semibold text-slate-600">{label}</span>
                                <span className="text-[11px] font-black text-slate-700 tabular-nums">{score}/{max}</span>
                            </div>
                            <div className="h-1.5 bg-slate-200 rounded-full overflow-hidden">
                                <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
                            </div>
                            {note && <p className="text-[10px] text-slate-500 leading-tight mt-0.5">{note}</p>}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

function getRelativeDate(dateStr, t) {
    if (!dateStr) return '';
    const diff = Math.floor((Date.now() - new Date(dateStr)) / 86400000);
    if (diff === 0) return t('today');
    if (diff === 1) return t('yesterday');
    return `${diff} ${t('daysAgo')}`;
}

export default function JobDetailPanel({
    job, onJobUpdated, onJobDeleted,
    provider, apiKey, modelName, downloadPath, userCode = '',
    cvList = [], addToast
}) {
    const { t } = useLanguage();

    // Edit state
    const [isEditing, setIsEditing] = useState(false);
    const [editCompany, setEditCompany] = useState(job.company || '');
    const [editTitle, setEditTitle] = useState(job.title || '');

    // Studio shared state
    const [studioMode, setStudioMode] = useState('letter');
    const [language, setLanguage] = useState('EN');
    const [localModel, setLocalModel] = useState(modelName);
    const [draft, setDraft] = useState('');
    const [selectedCvId, setSelectedCvId] = useState('');

    // Letter state
    const [letter, setLetter] = useState(job.motivation_letter || '');
    const [generating, setGenerating] = useState(false);
    const [exporting, setExporting] = useState(false);
    const [copied, setCopied] = useState(false);

    // CV Summary state
    const [cvSummary, setCvSummary] = useState(job.cv_summary || '');
    const [cvFullText, setCvFullText] = useState('');
    const [pdfUrl, setPdfUrl] = useState('');
    const [cvGenerating, setCvGenerating] = useState(false);
    const [cvCompiling, setCvCompiling] = useState(false);
    const [cvExporting, setCvExporting] = useState(false);
    const [cvMaxChars, setCvMaxChars] = useState(680);
    const [cvMaxCharsInput, setCvMaxCharsInput] = useState('680');
    const [cvCopied, setCvCopied] = useState(false);

    useEffect(() => { setLocalModel(modelName); }, [modelName]);

    useEffect(() => {
        if (cvList.length > 0 && !selectedCvId) {
            const active = cvList.find(c => c.is_active) || cvList[0];
            setSelectedCvId(active?.id || '');
        }
    }, [cvList]);

    const handleStatusChange = async (e) => {
        try {
            const updated = await updateJobStatus(job.id, e.target.value);
            onJobUpdated(updated);
        } catch { addToast(t('updateFailed'), 'error'); }
    };

    const handleSaveEdit = async () => {
        try {
            const updated = await updateJobDetails(job.id, editTitle, editCompany);
            onJobUpdated(updated);
            setIsEditing(false);
        } catch { addToast(t('updateFailed'), 'error'); }
    };

    const handleDelete = async () => {
        if (!window.confirm(t('confirmDelete'))) return;
        try {
            await deleteJob(job.id);
            onJobDeleted(job.id);
        } catch { addToast(t('deleteFailed'), 'error'); }
    };

    const handleGenerateLetter = async () => {
        setGenerating(true);
        try {
            const res = await generateLetter(job.id, language, draft, provider, apiKey, localModel);
            setLetter(res.letter);
        } catch (err) {
            const detail = err.response?.data?.detail || err.message || '';
            addToast(`${t('letterError')} ${detail}`, 'error');
        } finally { setGenerating(false); }
    };

    const handleGenerateCVSummary = async () => {
        setCvGenerating(true);
        setCvSummary('');
        setCvFullText('');
        setPdfUrl('');
        try {
            const res = await generateCVSummary(job.id, selectedCvId, language, draft, provider, apiKey, localModel, cvMaxChars);
            setCvSummary(res.summary);
            setCvFullText(res.full_cv);
            if (res.pdf_url) setPdfUrl(`http://localhost:8000${res.pdf_url}?t=${Date.now()}`);
        } catch (err) {
            const detail = err.response?.data?.detail || err.message || '';
            addToast(detail || 'CV özeti oluşturulamadı.', 'error');
        } finally { setCvGenerating(false); }
    };

    const handleExportLetter = async () => {
        if (!downloadPath) { addToast(t('noPathError'), 'error'); return; }
        if (!letter.trim()) return;
        setExporting(true);
        try {
            const res = await exportLetter(letter, job.company, downloadPath, job.id, userCode, job.title);
            addToast(`${t('letterSaved')}${res.saved_path}`, 'success');
        } catch (err) {
            addToast(`${t('downloadError')}${err.response?.data?.detail || err.message}`, 'error');
        } finally { setExporting(false); }
    };

    const handleExportCV = async () => {
        if (!downloadPath) { addToast(t('noPathError'), 'error'); return; }
        setCvExporting(true);
        try {
            const res = await exportCV(job.id, job.company, downloadPath, userCode);
            addToast(`Kaydedildi: ${res.saved_path}`, 'success');
        } catch (err) {
            addToast(`Kayıt hatası: ${err.response?.data?.detail || err.message}`, 'error');
        } finally { setCvExporting(false); }
    };

    const handleCopyLetter = async () => {
        if (!letter.trim()) return;
        await navigator.clipboard.writeText(letter);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const handleCopyCV = async () => {
        if (!cvFullText.trim()) return;
        await navigator.clipboard.writeText(cvFullText);
        setCvCopied(true);
        setTimeout(() => setCvCopied(false), 2000);
    };

    const handleRecompile = async () => {
        if (!cvSummary.trim()) return;
        setCvCompiling(true);
        try {
            const res = await recompileCV(job.id, selectedCvId, cvSummary);
            if (res.pdf_url) setPdfUrl(`http://localhost:8000${res.pdf_url}?t=${Date.now()}`);
            addToast('PDF yenilendi.', 'success');
        } catch (err) {
            addToast(err.response?.data?.detail || 'Derleme başarısız.', 'error');
        } finally { setCvCompiling(false); }
    };

    const statusStyle = STATUS_STYLES[job.status] || 'bg-slate-50 text-slate-600 border-slate-200';
    const selectedCv = cvList.find(c => c.id === selectedCvId);
    const isLatex = selectedCv?.filename?.toLowerCase().endsWith('.tex') ?? false;
    const isGenerating = studioMode === 'letter' ? generating : cvGenerating;
    const hasOutput = studioMode === 'letter' ? !!letter : !!cvSummary;

    return (
        <div className="max-w-3xl mx-auto px-8 py-7">

            {/* ── Job Header ── */}
            <div className="flex items-start justify-between gap-4 mb-7">
                <div className="flex-1 min-w-0">
                    {isEditing ? (
                        <div className="space-y-2">
                            <input autoFocus value={editCompany} onChange={e => setEditCompany(e.target.value)}
                                className="w-full text-2xl font-extrabold text-slate-800 border-b-2 border-indigo-400 bg-indigo-50/40 px-2 py-1 focus:outline-none rounded-t" />
                            <input value={editTitle} onChange={e => setEditTitle(e.target.value)}
                                className="w-full text-base font-semibold text-indigo-600 border-b-2 border-indigo-300 bg-indigo-50/40 px-2 py-1 focus:outline-none rounded-t" />
                            <div className="flex gap-2 pt-1">
                                <button onClick={handleSaveEdit} className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white text-xs font-bold rounded-lg">
                                    <Check className="w-3.5 h-3.5" />{t('save')}
                                </button>
                                <button onClick={() => { setEditCompany(job.company || ''); setEditTitle(job.title || ''); setIsEditing(false); }}
                                    className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 text-slate-600 text-xs font-bold rounded-lg">
                                    <X className="w-3.5 h-3.5" />{t('cancel')}
                                </button>
                            </div>
                        </div>
                    ) : (
                        <>
                            <div className="flex items-center gap-2 group">
                                <h2 className="text-2xl font-extrabold text-slate-800 leading-tight uppercase">
                                    {job.company || t('unknown')}
                                </h2>
                                <button onClick={() => setIsEditing(true)}
                                    className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-indigo-500 transition-all p-1 rounded">
                                    <Edit2 className="w-4 h-4" />
                                </button>
                            </div>
                            <p className="text-base font-semibold text-indigo-600 mt-0.5">{job.title || t('unknown')}</p>
                        </>
                    )}
                    {!isEditing && (
                        <div className="flex flex-wrap items-center gap-4 mt-3 text-sm text-slate-500">
                            {job.location && (
                                <span className="flex items-center gap-1.5 font-medium">
                                    <MapPin className="w-4 h-4 text-slate-400" />{job.location}
                                </span>
                            )}
                            <span className="text-slate-400 text-xs">{getRelativeDate(job.created_at, t)}</span>
                            {job.link && (
                                <a href={job.link} target="_blank" rel="noreferrer"
                                    className="flex items-center gap-1 text-indigo-500 hover:text-indigo-700 font-semibold text-xs transition-colors">
                                    <ExternalLink className="w-3.5 h-3.5" />{t('viewPosting')}
                                </a>
                            )}
                        </div>
                    )}
                </div>

                {!isEditing && (
                    <div className="flex items-center gap-2 shrink-0">
                        <select value={job.status} onChange={handleStatusChange}
                            className={`text-xs font-bold border rounded-xl px-3 py-2 cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500 ${statusStyle}`}>
                            <option value="Yeni">{t('new')}</option>
                            <option value="Başvuruldu">{t('applied')}</option>
                            <option value="Mülakat">{t('interview')}</option>
                            <option value="Reddedildi">{t('rejected')}</option>
                        </select>
                        <button onClick={handleDelete}
                            className="p-2 rounded-xl text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors">
                            <Trash2 className="w-4 h-4" />
                        </button>
                    </div>
                )}
            </div>

            {/* ── AI Analysis ── */}
            <Section title={t('aiAnalysis')} icon={<FileText className="w-4 h-4" />}>
                <div className="flex gap-6 items-start">
                    <ScoreRing score={job.score} />
                    <div className="flex-1 min-w-0 space-y-3">
                        {job.summary_tr ? (
                            <div className="space-y-2">{renderSummary(job.summary_tr)}</div>
                        ) : (
                            <p className="text-sm text-slate-400 italic">{t('noAnalysis')}</p>
                        )}
                        {job.language_reqs && (
                            <div className="flex flex-wrap gap-2 pt-1">
                                <span className="inline-flex items-center gap-1.5 bg-indigo-50 border border-indigo-100 text-indigo-700 text-xs font-bold px-3 py-1.5 rounded-lg">
                                    <Languages className="w-3.5 h-3.5" />
                                    {t('langReq')} {job.language_reqs}
                                </span>
                            </div>
                        )}
                        {job.language_explanation && (
                            <div className="bg-slate-50 border border-slate-100 rounded-xl p-3">
                                <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1">{t('langExplanation')}</p>
                                <p className="text-xs text-slate-600 leading-relaxed">{job.language_explanation}</p>
                            </div>
                        )}
                        <ScoreBreakdown breakdownJson={job.score_breakdown} />
                    </div>
                </div>
            </Section>

            {/* ── Studio ── */}
            <div className="mb-7">
                {/* Studio header */}
                <div className="flex items-center gap-2 mb-3">
                    <span className="text-indigo-500"><Wand2 className="w-4 h-4" /></span>
                    <h3 className="text-sm font-extrabold text-slate-700 uppercase tracking-wide">Studio</h3>
                    <div className="flex-1 h-px bg-slate-100 ml-1" />
                </div>

                <div className="bg-slate-50 border border-slate-100 rounded-2xl overflow-hidden">

                    {/* Mode tabs */}
                    <div className="flex border-b border-slate-200">
                        <button
                            onClick={() => setStudioMode('letter')}
                            className={`flex items-center gap-2 px-5 py-3.5 text-xs font-bold transition-colors border-b-2 -mb-px ${
                                studioMode === 'letter'
                                    ? 'border-slate-900 text-slate-900 bg-white'
                                    : 'border-transparent text-slate-500 hover:text-slate-700 bg-slate-50'
                            }`}
                        >
                            <Mail className="w-3.5 h-3.5" />
                            Motivasyon Mektubu
                        </button>
                        <button
                            onClick={() => setStudioMode('cv')}
                            className={`flex items-center gap-2 px-5 py-3.5 text-xs font-bold transition-colors border-b-2 -mb-px ${
                                studioMode === 'cv'
                                    ? 'border-indigo-600 text-indigo-700 bg-white'
                                    : 'border-transparent text-slate-500 hover:text-slate-700 bg-slate-50'
                            }`}
                        >
                            <User className="w-3.5 h-3.5" />
                            CV Özet
                        </button>
                    </div>

                    <div className="p-5">
                        {/* ── Config bar (shared) ── */}
                        <div className="flex flex-wrap items-center gap-3 mb-5 p-3 bg-white rounded-xl border border-slate-200 shadow-sm">

                            {/* CV selector */}
                            <div className="flex items-center gap-1.5">
                                <FileText className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                                {cvList.length > 0 ? (
                                    <div className="relative">
                                        <select
                                            value={selectedCvId}
                                            onChange={e => setSelectedCvId(e.target.value)}
                                            className="appearance-none pl-2 pr-6 py-1.5 rounded-lg border border-slate-200 text-xs font-semibold text-slate-700 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer"
                                        >
                                            {cvList.map(cv => (
                                                <option key={cv.id} value={cv.id}>
                                                    {cv.is_active ? '★ ' : ''}{cv.name}{!cv.has_file ? ' (boş)' : ''}
                                                </option>
                                            ))}
                                        </select>
                                        <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-400 pointer-events-none" />
                                    </div>
                                ) : (
                                    <span className="text-xs text-red-500 font-semibold">CV yüklenmemiş</span>
                                )}
                            </div>

                            <div className="w-px h-4 bg-slate-200" />

                            {/* Language toggle */}
                            <div className="flex rounded-lg border border-slate-200 overflow-hidden">
                                {['EN', 'DE'].map(l => (
                                    <button key={l} onClick={() => setLanguage(l)}
                                        className={`px-3 py-1.5 text-xs font-bold transition-colors ${
                                            language === l ? 'bg-indigo-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'
                                        }`}>
                                        {l === 'EN' ? '🇬🇧 EN' : '🇩🇪 DE'}
                                    </button>
                                ))}
                            </div>

                            <div className="w-px h-4 bg-slate-200" />

                            {/* Model */}
                            <div className="flex items-center gap-1.5">
                                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Model</span>
                                <div className="relative">
                                    <select
                                        value={localModel}
                                        onChange={e => setLocalModel(e.target.value)}
                                        className="appearance-none pl-2 pr-6 py-1.5 rounded-lg border border-slate-200 text-xs font-semibold text-slate-700 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer"
                                    >
                                        {AI_MODELS[provider]?.map(m => (
                                            <option key={m.id} value={m.id}>{m.name}</option>
                                        ))}
                                    </select>
                                    <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-400 pointer-events-none" />
                                </div>
                            </div>
                        </div>

                        {/* ── CV mode info banner ── */}
                        {studioMode === 'cv' && (
                            <div className="flex items-start gap-2.5 bg-indigo-50 border border-indigo-100 rounded-xl px-4 py-3 mb-4 text-xs text-indigo-700">
                                <Info className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                                <span>
                                    LaTeX CV'nizdeki özet bölümü otomatik tespit edilir. AI yalnızca summary metnini üretir (max {cvMaxChars} karakter), <code className="font-mono text-indigo-800">.tex</code> derlenir ve PDF önizlemesi gösterilir.
                                </span>
                            </div>
                        )}

                        {/* ── Draft textarea ── */}
                        <textarea
                            rows={studioMode === 'cv' ? 2 : 3}
                            placeholder={
                                studioMode === 'letter'
                                    ? t('draftPlaceholder')
                                    : 'Öne çıkarılacak özellikler, özel notlar... (opsiyonel)'
                            }
                            value={draft}
                            onChange={e => setDraft(e.target.value)}
                            className="w-full border border-slate-200 rounded-xl p-3.5 text-sm text-slate-700 focus:ring-2 focus:ring-indigo-500 focus:outline-none resize-none mb-4 transition-shadow placeholder:text-slate-400 bg-white"
                        />

                        {/* ── CV char limit selector ── */}
                        {studioMode === 'cv' && (
                            <div className="flex items-center gap-2 mb-3">
                                <span className="text-xs text-slate-500 shrink-0">Karakter limiti:</span>
                                <div className="flex rounded-lg border border-slate-200 overflow-hidden text-xs font-mono">
                                    {[480, 580, 680].map(n => (
                                        <button
                                            key={n}
                                            onClick={() => { setCvMaxChars(n); setCvMaxCharsInput(String(n)); }}
                                            className={`px-3 py-1.5 transition-colors ${cvMaxChars === n ? 'bg-indigo-600 text-white' : 'bg-white text-slate-500 hover:bg-slate-50'}`}
                                        >{n}</button>
                                    ))}
                                </div>
                                <input
                                    type="number"
                                    value={cvMaxCharsInput}
                                    onChange={e => {
                                        setCvMaxCharsInput(e.target.value);
                                        const v = parseInt(e.target.value);
                                        if (!isNaN(v) && v >= 200 && v <= 1500) setCvMaxChars(v);
                                    }}
                                    onBlur={() => {
                                        const v = parseInt(cvMaxCharsInput);
                                        const clamped = isNaN(v) ? 680 : Math.max(200, Math.min(1500, v));
                                        setCvMaxChars(clamped);
                                        setCvMaxCharsInput(String(clamped));
                                    }}
                                    className="w-16 border border-slate-200 rounded-lg px-2 py-1.5 text-xs font-mono text-slate-700 text-center focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                                />
                            </div>
                        )}

                        {/* ── Generate button ── */}
                        <button
                            onClick={studioMode === 'letter' ? handleGenerateLetter : handleGenerateCVSummary}
                            disabled={isGenerating || cvList.length === 0}
                            className={`w-full text-white text-sm font-bold py-3.5 rounded-xl transition-colors shadow-sm flex items-center justify-center gap-2 disabled:opacity-50 ${
                                studioMode === 'letter'
                                    ? 'bg-slate-900 hover:bg-black'
                                    : 'bg-indigo-600 hover:bg-indigo-700'
                            }`}
                        >
                            {isGenerating ? (
                                <><span className="animate-spin inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full" />
                                {studioMode === 'letter' ? t('generating') : 'Özet oluşturuluyor...'}</>
                            ) : (
                                <><Wand2 className="w-4 h-4" />
                                {studioMode === 'letter' ? t('createMotivation') : 'CV Özeti Oluştur'}</>
                            )}
                        </button>

                        {/* ── Letter output ── */}
                        {studioMode === 'letter' && (
                            letter ? (
                                <div className="mt-5 space-y-3">
                                    <div className="flex items-center justify-between">
                                        <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">Motivation Letter</p>
                                        <button onClick={handleCopyLetter}
                                            className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-700 transition-colors">
                                            {copied
                                                ? <><CheckCheck className="w-3.5 h-3.5 text-emerald-500" />{t('copied')}</>
                                                : <><Copy className="w-3.5 h-3.5" />{t('copyLetter')}</>
                                            }
                                        </button>
                                    </div>
                                    <textarea value={letter} onChange={e => setLetter(e.target.value)} rows={18}
                                        className="w-full border border-slate-200 rounded-xl p-4 text-sm text-slate-700 font-mono leading-relaxed focus:ring-2 focus:ring-indigo-500 focus:outline-none resize-none transition-shadow bg-white" />
                                    <button onClick={handleExportLetter} disabled={exporting}
                                        className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white text-sm font-bold py-3 rounded-xl transition-colors flex items-center justify-center gap-2">
                                        <Download className="w-4 h-4" />
                                        {exporting ? t('downloading') : 'PDF Olarak Kaydet'}
                                    </button>
                                </div>
                            ) : (
                                <p className="text-xs text-slate-400 text-center mt-4">{t('noLetterYet')}</p>
                            )
                        )}

                        {/* ── CV Summary output ── */}
                        {studioMode === 'cv' && cvSummary && (
                            <div className="mt-5 space-y-4">
                                {/* Generated summary highlight — editable */}
                                <div className="relative bg-gradient-to-br from-indigo-50 to-indigo-100/50 border border-indigo-200 rounded-xl p-4">
                                    <div className="flex items-center gap-2 mb-2.5">
                                        <div className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse" />
                                        <span className="text-[10px] font-extrabold text-indigo-600 uppercase tracking-widest">
                                            Oluşturulan Profil Özeti
                                        </span>
                                        <span className="text-[9px] text-indigo-300 font-medium ml-1">— düzenleyebilirsiniz</span>
                                        {selectedCv && (
                                            <span className="ml-auto text-[10px] font-bold text-indigo-400">
                                                {selectedCv.name}
                                            </span>
                                        )}
                                    </div>
                                    <textarea
                                        value={cvSummary}
                                        onChange={e => setCvSummary(e.target.value)}
                                        rows={4}
                                        className="w-full text-sm text-indigo-900 leading-relaxed font-medium bg-transparent border-0 outline-none resize-none focus:ring-0 p-0 placeholder:text-indigo-300"
                                        placeholder="Özet metni burada görünecek..."
                                    />
                                    <div className="flex items-center justify-between mt-2">
                                        <span className={`text-[9px] font-mono ${cvSummary.length > cvMaxChars ? 'text-red-500' : 'text-indigo-300'}`}>
                                            {cvSummary.length}/{cvMaxChars}
                                        </span>
                                        {isLatex && (
                                            <button
                                                onClick={handleRecompile}
                                                disabled={cvCompiling || !cvSummary.trim()}
                                                className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white text-[10px] font-bold rounded-lg transition-colors"
                                            >
                                                {cvCompiling
                                                    ? <><span className="w-3 h-3 border border-white/40 border-t-white rounded-full animate-spin" />Derleniyor...</>
                                                    : <><Wand2 className="w-3 h-3" />PDF'e Derle</>
                                                }
                                            </button>
                                        )}
                                    </div>
                                </div>

                                {pdfUrl ? (
                                    /* PDF Preview — .tex başarıyla derlendi */
                                    <div className="space-y-2">
                                        <div className="flex items-center justify-between">
                                            <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">PDF Önizleme</p>
                                            <button onClick={handleCopyCV}
                                                className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-700 transition-colors">
                                                {cvCopied
                                                    ? <><CheckCheck className="w-3.5 h-3.5 text-emerald-500" />LaTeX kopyalandı</>
                                                    : <><Copy className="w-3.5 h-3.5" />LaTeX kopyala</>
                                                }
                                            </button>
                                        </div>
                                        <iframe
                                            src={pdfUrl}
                                            className="w-full rounded-xl border border-slate-200"
                                            style={{ height: '720px' }}
                                            title="CV Önizleme"
                                        />
                                        <button onClick={handleExportCV} disabled={cvExporting}
                                            className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white text-sm font-bold py-3 rounded-xl transition-colors flex items-center justify-center gap-2">
                                            <Download className="w-4 h-4" />
                                            {cvExporting ? 'Kaydediliyor...' : 'CV PDF Kaydet'}
                                        </button>
                                    </div>
                                ) : isLatex ? (
                                    /* .tex yüklü ama henüz derlenmedi */
                                    <div className="bg-slate-50 border border-dashed border-slate-200 rounded-xl p-6 text-center">
                                        <p className="text-xs text-slate-400 font-medium">
                                            Özet oluşturulduktan sonra <span className="font-mono text-indigo-500">.tex</span> otomatik derlenir ve PDF burada görünür.
                                        </p>
                                    </div>
                                ) : (
                                    /* .tex değil — LaTeX workflow kullanılamaz */
                                    <div className="bg-amber-50 border border-amber-100 rounded-xl p-4 text-xs text-amber-700">
                                        PDF önizleme yalnızca LaTeX (.tex) CV'lerde çalışır. CV Yönetiminden bir .tex dosyası yükleyin.
                                    </div>
                                )}
                            </div>
                        )}

                        {studioMode === 'cv' && !cvSummary && !cvGenerating && (
                            <p className="text-xs text-slate-400 text-center mt-4">
                                CV dosyanıza <code className="font-mono">[PLACEHOLDER]</code> ekleyin, ardından oluşturun.
                            </p>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

function Section({ title, icon, children }) {
    return (
        <div className="mb-7">
            <div className="flex items-center gap-2 mb-4">
                <span className="text-indigo-500">{icon}</span>
                <h3 className="text-sm font-extrabold text-slate-700 uppercase tracking-wide">{title}</h3>
                <div className="flex-1 h-px bg-slate-100 ml-1" />
            </div>
            <div className="bg-slate-50 border border-slate-100 rounded-2xl p-5">
                {children}
            </div>
        </div>
    );
}
