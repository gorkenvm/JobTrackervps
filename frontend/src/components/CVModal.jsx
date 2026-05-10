import React, { useState, useEffect } from 'react';
import { Plus, Trash2, Upload, FileText } from 'lucide-react';
import { listCVs, addCV, uploadCVFile, renameCV, activateCV, deleteCV } from '../services/api';

const EXT_COLORS = {
    PDF: 'bg-red-500',
    TEX: 'bg-orange-500',
    TXT: 'bg-slate-500',
    MD:  'bg-blue-500',
};

const LINE_WIDTHS = [100, 82, 96, 68, 100, 74, 88, 55, 100, 71, 92, 63, 100, 78, 85, 60];

export default function CVModal({ onClose, addToast, onCVChanged }) {
    const [cvs, setCVs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [editNames, setEditNames] = useState({});

    const load = async () => {
        try {
            const data = await listCVs();
            setCVs(data);
            const names = {};
            data.forEach(cv => { names[cv.id] = cv.name; });
            setEditNames(names);
        } catch {
            addToast('CV listesi yüklenemedi.', 'error');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { load(); }, []);

    const handleAdd = async () => {
        try {
            const newCV = await addCV(`CV${cvs.length + 1}`);
            setCVs(prev => [...prev, newCV]);
            setEditNames(prev => ({ ...prev, [newCV.id]: newCV.name }));
            onCVChanged?.();
        } catch {
            addToast('CV eklenemedi.', 'error');
        }
    };

    const handleRename = async (cvId) => {
        const name = (editNames[cvId] ?? '').trim();
        if (!name) return;
        const cv = cvs.find(c => c.id === cvId);
        if (cv?.name === name) return;
        try {
            await renameCV(cvId, name);
            setCVs(prev => prev.map(c => c.id === cvId ? { ...c, name } : c));
        } catch {
            addToast('İsim değiştirilemedi.', 'error');
        }
    };

    const handleUpload = async (cvId, file) => {
        try {
            await uploadCVFile(cvId, file);
            await activateCV(cvId);
            const ext = file.name.slice(file.name.lastIndexOf('.'));
            setCVs(prev => prev.map(c => ({
                ...c,
                is_active: c.id === cvId,
                has_file: c.id === cvId ? true : c.has_file,
                filename: c.id === cvId ? `${c.id}${ext}` : c.filename,
            })));
            onCVChanged?.();
            addToast('CV yüklendi.', 'success');
        } catch {
            addToast('CV yüklenemedi.', 'error');
        }
    };

    const handleDelete = async (cvId) => {
        try {
            await deleteCV(cvId);
            onCVChanged?.();
            addToast('CV silindi.', 'success');
            await load();
        } catch {
            addToast('CV silinemedi.', 'error');
        }
    };

    if (loading) {
        return (
            <div className="p-12 flex items-center justify-center">
                <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
            </div>
        );
    }

    return (
        <div className="p-7 w-full">
            <div className="flex items-start justify-between mb-1">
                <div>
                    <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                        <FileText className="w-5 h-5 text-indigo-600" />
                        CV Yönetimi
                    </h2>
                    <p className="text-xs text-slate-400 mt-0.5">
                        Studio'da hangi CV kullanılacağını seçebilirsiniz · .md .txt .tex .pdf desteklenir
                    </p>
                </div>
            </div>

            <div className="mt-5 grid grid-cols-3 gap-5">
                {cvs.map(cv => (
                    <CVCard
                        key={cv.id}
                        cv={cv}
                        editName={editNames[cv.id] ?? cv.name}
                        onNameChange={val => setEditNames(prev => ({ ...prev, [cv.id]: val }))}
                        onRename={() => handleRename(cv.id)}
                        onUpload={file => handleUpload(cv.id, file)}
                        onDelete={() => handleDelete(cv.id)}
                    />
                ))}

                <button
                    onClick={handleAdd}
                    className="flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-slate-200 text-slate-400 hover:border-indigo-400 hover:text-indigo-500 hover:bg-indigo-50 transition-all"
                    style={{ aspectRatio: '5 / 7' }}
                >
                    <div className="w-12 h-12 rounded-full border-2 border-current flex items-center justify-center">
                        <Plus className="w-5 h-5" />
                    </div>
                    <span className="text-xs font-bold">Yeni CV</span>
                </button>
            </div>

            <div className="mt-6 pt-4 border-t border-slate-100 flex justify-end">
                <button
                    onClick={onClose}
                    className="px-5 py-2 text-sm font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl transition-colors"
                >
                    Kapat
                </button>
            </div>
        </div>
    );
}

function CVCard({ cv, editName, onNameChange, onRename, onUpload, onDelete }) {
    const ext = (cv.filename?.split('.').pop() || 'md').toUpperCase();
    const badgeColor = EXT_COLORS[ext] || 'bg-slate-500';

    return (
        <div
            className="flex flex-col rounded-2xl border-2 border-slate-200 overflow-hidden shadow-sm hover:border-slate-300 hover:shadow-md transition-all"
            style={{ aspectRatio: '5 / 7' }}
        >
            {/* Document body */}
            <div className="flex-1 flex flex-col bg-slate-50 min-h-0">
                {cv.has_file ? (
                    <DocumentPreview ext={ext} badgeColor={badgeColor} />
                ) : (
                    <label className="flex-1 flex flex-col items-center justify-center gap-2 cursor-pointer p-4 text-slate-300 hover:text-indigo-400 hover:bg-indigo-50 transition-colors">
                        <Upload className="w-8 h-8" />
                        <span className="text-[10px] font-bold text-center leading-tight text-slate-400">
                            Dosya Yükle
                        </span>
                        <span className="text-[9px] text-slate-300 font-medium">.md .txt .tex .pdf</span>
                        <input
                            type="file"
                            accept=".md,.txt,.tex,.pdf"
                            className="hidden"
                            onChange={e => {
                                if (e.target.files?.[0]) onUpload(e.target.files[0]);
                                e.target.value = '';
                            }}
                        />
                    </label>
                )}
            </div>

            {/* Footer */}
            <div className="flex-shrink-0 px-3 pt-2.5 pb-2.5 flex flex-col gap-2 bg-white border-t border-slate-100">
                <input
                    type="text"
                    value={editName}
                    onChange={e => onNameChange(e.target.value)}
                    onBlur={onRename}
                    onKeyDown={e => e.key === 'Enter' && e.target.blur()}
                    className="w-full text-xs font-bold bg-transparent border-b border-transparent outline-none text-center text-slate-700 hover:border-slate-200 focus:border-indigo-400 transition-colors pb-0.5"
                    placeholder="CV adı..."
                />
                <div className="flex items-center justify-between">
                    <span className={`text-[9px] font-bold ${cv.has_file ? 'text-emerald-500' : 'text-slate-300'}`}>
                        {cv.has_file ? `● ${ext}` : '○ Boş'}
                    </span>
                    <div className="flex items-center gap-1">
                        <label
                            className="p-1.5 rounded-lg cursor-pointer text-slate-400 hover:text-indigo-600 hover:bg-indigo-100 transition-colors"
                            title="Dosya yükle / değiştir"
                        >
                            <Upload className="w-3.5 h-3.5" />
                            <input
                                type="file"
                                accept=".md,.txt,.tex,.pdf"
                                className="hidden"
                                onChange={e => {
                                    if (e.target.files?.[0]) onUpload(e.target.files[0]);
                                    e.target.value = '';
                                }}
                            />
                        </label>
                        <button
                            onClick={onDelete}
                            className="p-1.5 rounded-lg text-slate-300 hover:text-red-500 hover:bg-red-50 transition-colors"
                            title="CV'yi sil"
                        >
                            <Trash2 className="w-3.5 h-3.5" />
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

function DocumentPreview({ ext, badgeColor }) {
    return (
        <div className="flex-1 flex flex-col p-4 gap-2 min-h-0 overflow-hidden">
            <div className="flex items-center gap-2 flex-shrink-0">
                <div className={`rounded-md px-2 py-0.5 ${badgeColor}`}>
                    <span className="text-[9px] font-black text-white tracking-tight">{ext}</span>
                </div>
            </div>
            <div className="flex-1 flex flex-col justify-start gap-1.5 overflow-hidden pt-1">
                {LINE_WIDTHS.map((w, i) => (
                    <div
                        key={i}
                        className="rounded-full flex-shrink-0 bg-slate-200"
                        style={{ width: `${w}%`, height: '4px' }}
                    />
                ))}
            </div>
        </div>
    );
}
