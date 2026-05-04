import React, { useState, useEffect } from "react";
import { Layout, Row, Col, Card } from "antd";
import "./index.css";
import Home from "./pages/Home";
import Domains from "./pages/Domains";
import ShopAnalysis from "./pages/ShopAnalysis";
import GovernanceControlPlane from "./pages/GovernanceControlPlane";
import GovernancePrioritization from "./pages/GovernancePrioritization";
import SilverToDomainLoader from "./pages/SilverToDomainLoader";
import Catalog from "./pages/Catalog";
import PipelineMonitoring from "./pages/PipelineMonitoring";
import DomainHealthDashboard from "./components/DomainHealthDashboard";
import { API_BASE } from "./config";

const { Content } = Layout;

const DOMAIN_CARDS = [
  { key: "users_domain", name: "Users Domain", description: "Handles user registration and user master data." },
  { key: "product_domain", name: "Product Domain", description: "Manages product catalog and product master data." },
  { key: "sales_domain", name: "Sales Domain", description: "Owns sales transactions and shop sales activity." },
  { key: "shop_domain", name: "Shop Domain", description: "Manages shop registration, metadata, and mesh participation." },
  { key: "user_preferences_domain", name: "User Preferences Domain", description: "Owns user preferences and personalization data." },
  { key: "engagement_domain", name: "Engagement Domain", description: "Tracks user engagement and interaction events." },
  { key: "interaction_domain", name: "Interaction Domain", description: "Handles user interaction events." },
];

const NAV_TABS = [
  { key: "overview", label: "Overview" },
  { key: "domains", label: "Domains" },
  { key: "products", label: "Data Products" },
  { key: "shop", label: "Shop Analysis" },
  { key: "pipeline-monitoring", label: "Pipeline Monitoring" },
  { key: "domain-analytics", label: "Domain Analytics" },
  { key: "governance", label: "Governance" },
  { key: "governance-prioritization", label: "Prioritization" },
  { key: "silver-domain-loader", label: "Semantic Assignment" },
  { key: "mlhealth", label: "ML Health" },
];

export default function App() {
  const [selected, setSelected] = useState("overview");
  const [activeDomain, setActiveDomain] = useState(null); // Track which domain card is clicked

  return (
    <Layout className="dm-shell" style={{ minHeight: "100%", height: "100%", width: "100%", overflow: "hidden", background: "#f5f6fa" }}>
      <Content style={{ padding: 16, background: "#f5f6fa", minHeight: 0, minWidth: 0, width: "100%", overflow: "auto" }}>
        <div
          style={{
            background: "#ffffff",
            border: "1px solid #e2e8f0",
            borderRadius: 12,
            padding: "14px 16px",
            marginBottom: 16,
            boxShadow: "0 1px 4px rgba(15, 23, 42, 0.06)",
          }}
        >
          <div style={{ fontSize: 24, fontWeight: 700, color: "#0f172a", lineHeight: 1.2 }}>
            Data Mesh Control Plane
          </div>
          <div style={{ fontSize: 14, color: "#64748b", marginTop: 6, lineHeight: 1.45 }}>
            Domain-oriented data access and semantic domain assignment for distributed ownership and discoverability.
          </div>
          <div style={{ marginTop: 14, overflowX: "auto", paddingBottom: 2 }}>
            <div style={{ display: "flex", gap: 8, minWidth: "max-content" }}>
              {NAV_TABS.map((tab) => {
                const active = selected === tab.key;
                return (
                  <button
                    key={tab.key}
                    type="button"
                    onClick={() => {
                      setSelected(tab.key);
                      setActiveDomain(null);
                    }}
                    style={{
                      height: 36,
                      borderRadius: 999,
                      padding: "0 14px",
                      border: active ? "none" : "1px solid #cbd5e1",
                      background: active ? "linear-gradient(90deg, #2563eb 0%, #4f46e5 100%)" : "#ffffff",
                      color: active ? "#ffffff" : "#0f172a",
                      fontWeight: 600,
                      fontSize: 13,
                      whiteSpace: "nowrap",
                      cursor: "pointer",
                      boxShadow: active ? "0 4px 12px rgba(37, 99, 235, 0.3)" : "none",
                    }}
                  >
                    {tab.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Mesh-native content routing */}
        {selected === "overview" && <Home />}
        {selected === "domains" && <Domains />}
        {selected === "products" && <Catalog />}
        {selected === "shop" && <ShopAnalysis />}
        {selected === "pipeline-monitoring" && <PipelineMonitoring />}
        {selected === "governance" && <GovernanceControlPlane />}
        {selected === "governance-prioritization" && <GovernancePrioritization />}
        {selected === "silver-domain-loader" && <SilverToDomainLoader />}
        {selected === "mlhealth" && (
          <div style={{ maxWidth: 1200, margin: "0 auto", background: "#fff", borderRadius: 14, border: "1px solid #e2e8f0", boxShadow: "0 8px 24px rgba(15, 23, 42, 0.06)", padding: "2rem 1.75rem" }}>
            <DomainHealthDashboard />
          </div>
        )}
        {selected === "domain-analytics" && (
          <div>
            <h1 style={{ fontWeight: 700, fontSize: 28, marginBottom: 24, color: "#0f172a" }}>Domain-wise Analytics</h1>
            {!activeDomain ? (
              <Row gutter={[20, 20]}>
                {DOMAIN_CARDS.map(domain => (
                  <Col xs={24} sm={12} md={8} lg={6} key={domain.key}>
                    <Card
                      hoverable
                      style={{ borderRadius: 12, minHeight: 158, boxShadow: "0 4px 14px rgba(15, 23, 42, 0.08)", border: "1px solid #e2e8f0", cursor: "pointer" }}
                      onClick={() => setActiveDomain(domain)}
                      bodyStyle={{ padding: 18 }}
                    >
                      <div style={{ fontWeight: 600, fontSize: 18, marginBottom: 8, color: "#0f172a" }}>{domain.name}</div>
                      <div style={{ color: "#64748b", fontSize: 14, lineHeight: 1.5 }}>{domain.description}</div>
                    </Card>
                  </Col>
                ))}
              </Row>
            ) : (
              <DomainDetailView domain={activeDomain} onBack={() => setActiveDomain(null)} />
            )}
          </div>
        )}
      </Content>
    </Layout>
  );
}

// Detailed view for each domain card
function DomainDetailView({ domain, onBack }) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);

  useEffect(() => {
    setLoading(true);
    fetch(`${API_BASE}/api/domain-metrics/${domain.key}`)
      .then(res => res.json())
      .then(json => {
        setData(json);
        setLoading(false);
      });
  }, [domain.key]);

  if (loading) return <div>Loading...</div>;
  if (!data || data.error) return <div>No data available.</div>;

  const { health, lastRefreshed, metrics } = data;

  return (
    <div style={{ background: '#fff', borderRadius: 16, boxShadow: '0 2px 16px #e0e7ef33', padding: '2.5rem 2rem', maxWidth: 800, margin: '0 auto' }}>
      <button onClick={onBack} style={{ marginBottom: 24, fontWeight: 600, fontSize: 16, background: '#eee', border: 'none', borderRadius: 8, padding: '8px 18px', cursor: 'pointer' }}>← Back to Domain Cards</button>
      <h2 style={{ fontWeight: 700, fontSize: 28, marginBottom: 16 }}>{domain.name} Details</h2>
      <p style={{ fontSize: 17, color: '#444', marginBottom: 24 }}>{domain.description}</p>
      <div style={{ display: 'flex', gap: 32, marginBottom: 32 }}>
        <div style={{ fontSize: 17 }}>
          <b>Health Status:</b> <span style={{ color: health === 'Healthy' ? '#22c55e' : '#f59e42', fontWeight: 700 }}>{health}</span>
        </div>
        <div style={{ fontSize: 17 }}>
          <b>Last Refreshed:</b> <span style={{ color: '#3b82f6', fontWeight: 600 }}>{lastRefreshed}</span>
        </div>
      </div>
      <div style={{ marginBottom: 24 }}>
        <h3 style={{ fontWeight: 600, fontSize: 20, marginBottom: 12 }}>Summary Metrics</h3>
        <ul style={{ fontSize: 16, color: '#555', lineHeight: 2 }}>
          {metrics.total !== undefined && <li><b>Total records:</b> {metrics.total.toLocaleString()}</li>}
          {metrics.newThisMonth !== undefined && <li><b>New this month:</b> {metrics.newThisMonth.toLocaleString()}</li>}
          {metrics.completeness && <li><b>Completeness:</b> {metrics.completeness}</li>}
          {metrics.errors !== undefined && <li><b>Errors/Anomalies:</b> {metrics.errors}</li>}
        </ul>
      </div>
      <ul style={{ fontSize: 16, color: '#555', lineHeight: 2 }}>
        <li><b>Domain Key:</b> {domain.key}</li>
        <li><b>Purpose:</b> {domain.description}</li>
        <li><b>Analytics:</b> Detailed metrics and charts for {domain.name} will appear here.</li>
      </ul>
    </div>
  );
}