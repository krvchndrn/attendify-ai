import axios from "axios";

// API base URL for Railway deployment
export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

const api = axios.create({ baseURL: API_BASE });

api.interceptors.request.use((config) => {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error.response?.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default api;

// ----- Houses -----
export const getHouses = () => api.get("/houses/").then((r) => r.data);
export const getHouse = (id: number) => api.get(`/houses/${id}`).then((r) => r.data);
export const adjustPoints = (id: number, points: number, reason: string) =>
  api.post(`/houses/${id}/adjust-points`, { points, reason }).then((r) => r.data);
export const getHouseHistory = (id: number) => api.get(`/houses/${id}/history`).then((r) => r.data);

// ----- Students -----
export const getStudents = (params?: Record<string, string>) =>
  api.get("/students/", { params }).then((r) => r.data);
export const getStudent = (id: number) => api.get(`/students/${id}`).then((r) => r.data);
export const getStudentsByClass = () => api.get("/students/by-class").then((r) => r.data);
export const createStudent = (form: FormData) =>
  api.post("/students/", form, { headers: { "Content-Type": "multipart/form-data" } }).then((r) => r.data);
export const updateStudent = (id: number, form: FormData) =>
  api.put(`/students/${id}`, form, { headers: { "Content-Type": "multipart/form-data" } }).then((r) => r.data);
export const deleteStudent = (id: number) => api.delete(`/students/${id}`).then((r) => r.data);
export const addStudentPhotos = (id: number, form: FormData) =>
  api.post(`/students/${id}/photos`, form, { headers: { "Content-Type": "multipart/form-data" } }).then((r) => r.data);

// ----- Late Entries -----
export const getLateEntries = (params?: Record<string, string>) =>
  api.get("/late-entries/", { params }).then((r) => r.data);
export const getReviewQueue = () => api.get("/late-entries/review-queue").then((r) => r.data);
export const createLateEntry = (data: object) => api.post("/late-entries/", data).then((r) => r.data);
export const updateLateEntry = (id: number, data: object) =>
  api.put(`/late-entries/${id}`, data).then((r) => r.data);

// ----- Analytics -----
export const getLateTrend = (params?: Record<string, string>) =>
  api.get("/analytics/late-trend", { params }).then((r) => r.data);
export const getHousePerformance = () => api.get("/analytics/house-performance").then((r) => r.data);
export const getFrequentOffenders = (params?: Record<string, string>) =>
  api.get("/analytics/frequent-offenders", { params }).then((r) => r.data);
export const getSummary = () => api.get("/analytics/summary").then((r) => r.data);
export const getExportUrl = (params?: Record<string, string>) => {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  return `${API_BASE}/analytics/export${qs}`;
};

// ----- Calendar -----
export const getCalendar = () => api.get("/calendar/").then((r) => r.data);
export const createCalendarEntry = (data: object) => api.post("/calendar/", data).then((r) => r.data);
export const deleteCalendarEntry = (id: number) => api.delete(`/calendar/${id}`).then((r) => r.data);

// ----- Auth -----
export const login = (email: string, password: string) => {
  const form = new URLSearchParams();
  form.append("username", email);
  form.append("password", password);
  return api
    .post("/auth/login", form, { headers: { "Content-Type": "application/x-www-form-urlencoded" } })
    .then((r) => r.data);
};
export const getMe = () => api.get("/auth/me").then((r) => r.data);
export const resetPassword = (id: number, newPassword: string) =>
  api.put(`/auth/users/${id}/reset-password`, { new_password: newPassword }).then((r) => r.data);
export const getActivityLog = (params?: Record<string, string>) =>
  api.get("/auth/activity-log", { params }).then((r) => r.data);

// ----- Chat -----
export const sendChatMessage = (message: string, history?: { role: string; content: string }[]) =>
  api.post("/chat", { message, history }).then((r) => r.data);

// ----- House Manager -----
export const getHouseManagerReport = (params?: Record<string, string>) =>
  api.get("/house-manager/report", { params }).then((r) => r.data);

export const downloadHouseManagerReport = async (houseName: string, weekStart: string, params?: Record<string, string>) => {
  const res = await api.get("/house-manager/report/export", { params, responseType: "blob" });
  const url = window.URL.createObjectURL(new Blob([res.data]));
  const a = document.createElement("a");
  a.href = url;
  a.download = `${houseName}_weekly_report_${weekStart}.xlsx`;
  a.click();
  window.URL.revokeObjectURL(url);
};
