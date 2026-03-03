import axios from "axios";
import { API_BASE } from "../config";

export const fetchUsers = () => axios.get(`${API_BASE}/users`).then(r => r.data);
export const fetchProducts = () => axios.get(`${API_BASE}/products`).then(r => r.data);
export const fetchSales = () => axios.get(`${API_BASE}/sales`).then(r => r.data);
export const fetchKPIs = () => axios.get(`${API_BASE}/kpis`).then(r => r.data);
export const fetchOverview = () => axios.get(`${API_BASE}/overview`).then(r => r.data);
export const fetchDataProducts = () => axios.get(`${API_BASE}/data-products`).then(r => r.data);