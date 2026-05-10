import axios from 'axios';

const API_URL = 'http://localhost:8000';

export const getJobs = async () => {
    const res = await axios.get(`${API_URL}/jobs/`);
    return res.data;
};

export const createJob = async (jobData) => {
    // jobData now includes link, description, provider, api_key
    const res = await axios.post(`${API_URL}/jobs/`, jobData);
    return res.data;
};

export const updateJobStatus = async (jobId, status) => {
    const res = await axios.put(`${API_URL}/jobs/${jobId}/status`, { status });
    return res.data;
};

export const updateJobDetails = async (jobId, title, company) => {
    const res = await axios.put(`${API_URL}/jobs/${jobId}/details`, { title, company });
    return res.data;
};

export const deleteJob = async (jobId) => {
    const res = await axios.delete(`${API_URL}/jobs/${jobId}`);
    return res.data;
};

export const uploadCV = async (file) => {
    const formData = new FormData();
    formData.append("file", file);
    const res = await axios.post(`${API_URL}/cv/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
    });
    return res.data;
};

export const getCVStatus = async () => {
    const res = await axios.get(`${API_URL}/cv/status`);
    return res.data;
};

export const uploadSample = async (file) => {
    const formData = new FormData();
    formData.append("file", file);
    const res = await axios.post(`${API_URL}/sample/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
    });
    return res.data;
};

export const getSampleStatus = async () => {
    const res = await axios.get(`${API_URL}/sample/status`);
    return res.data;
};

export const generateLetter = async (jobId, language, draft, provider, apiKey, modelName) => {
    const res = await axios.post(`${API_URL}/generate/letter`, {
        job_id: jobId,
        language,
        draft,
        provider: provider,
        api_key: apiKey,
        model_name: modelName
    });
    return res.data;
};

export const exportLetter = async (letterText, companyName, downloadPath, jobId = 0, userCode = "") => {
    const res = await axios.post(`${API_URL}/export/letter`, {
        letter_text: letterText,
        company_name: companyName,
        download_path: downloadPath,
        job_id: jobId,
        user_code: userCode,
    });
    return res.data;
};

export const exportCV = async (jobId, companyName, downloadPath, userCode = "") => {
    const res = await axios.post(`${API_URL}/export/cv`, {
        job_id: jobId,
        company_name: companyName,
        download_path: downloadPath,
        user_code: userCode,
    });
    return res.data;
};

export const getApifyConfig = async () => {
    const res = await axios.get(`${API_URL}/apify/config`);
    return res.data;
};

export const saveApifyConfig = async (config) => {
    const res = await axios.post(`${API_URL}/apify/config`, config);
    return res.data;
};

export const apifyFetchNow = async () => {
    const res = await axios.post(`${API_URL}/apify/fetch`, {});
    return res.data;
};

export const apifyFetchSingleUrl = async (url) => {
    const res = await axios.post(`${API_URL}/apify/fetch-url`, { url }, { timeout: 360000 });
    return res.data;
};

export const listCVs = async () => {
    const res = await axios.get(`${API_URL}/cv/list`);
    return res.data;
};

export const addCV = async (name) => {
    const res = await axios.post(`${API_URL}/cv/add`, { name });
    return res.data;
};

export const uploadCVFile = async (cvId, file) => {
    const formData = new FormData();
    formData.append("file", file);
    const res = await axios.post(`${API_URL}/cv/${cvId}/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
    });
    return res.data;
};

export const renameCV = async (cvId, name) => {
    const res = await axios.put(`${API_URL}/cv/${cvId}/name`, { name });
    return res.data;
};

export const activateCV = async (cvId) => {
    const res = await axios.put(`${API_URL}/cv/${cvId}/activate`);
    return res.data;
};

export const deleteCV = async (cvId) => {
    const res = await axios.delete(`${API_URL}/cv/${cvId}`);
    return res.data;
};

export const recompileCV = async (jobId, cvId, summaryText) => {
    const res = await axios.post(`${API_URL}/generate/cv-recompile`, {
        job_id: jobId,
        cv_id: cvId,
        summary_text: summaryText,
    });
    return res.data;
};

export const generateCVSummary = async (jobId, cvId, language, draft, provider, apiKey, modelName) => {
    const res = await axios.post(`${API_URL}/generate/cv-summary`, {
        job_id: jobId,
        cv_id: cvId,
        language,
        draft,
        provider,
        api_key: apiKey,
        model_name: modelName,
    });
    return res.data;
};

export const getSettings = async () => {
    const res = await axios.get(`${API_URL}/settings`);
    return res.data;
};

export const saveSettings = async (settings) => {
    const res = await axios.post(`${API_URL}/settings`, settings);
    return res.data;
};
