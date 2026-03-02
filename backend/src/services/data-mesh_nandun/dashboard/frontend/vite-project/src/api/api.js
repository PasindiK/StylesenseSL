import axios from "axios";
const BASE = "http://localhost:8000";

export const fetchUsers = () => axios.get(`${BASE}/users`).then(r => r.data);
export const fetchProducts = () => axios.get(`${BASE}/products`).then(r => r.data);
export const fetchSales = () => axios.get(`${BASE}/sales`).then(r => r.data);
export const fetchKPIs = () => axios.get(`${BASE}/kpis`).then(r => r.data);
export const fetchOverview = () => axios.get(`${BASE}/overview`).then(r => r.data);
export const fetchDataProducts = () => axios.get(`${BASE}/data-products`).then(r => r.data);