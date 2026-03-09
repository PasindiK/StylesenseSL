import React, { useState, useEffect } from "react";
import { Layout, Menu, Row, Col, Card } from "antd";
import "./index.css";
import {
  AppstoreOutlined,
  DatabaseOutlined,
  ShopOutlined,
  SafetyOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined
} from "@ant-design/icons";
import Home from "./pages/Home";
import Domains from "./pages/Domains";
import ShopAnalysis from "./pages/ShopAnalysis";
import GovernanceControlPlane from "./pages/GovernanceControlPlane";
import GovernancePrioritization from "./pages/GovernancePrioritization";
import Catalog from "./pages/Catalog";
import PipelineMonitoring from "./pages/PipelineMonitoring";
import DomainHealthDashboard from "./components/DomainHealthDashboard";
import { API_BASE } from "./config";

const { Sider, Content, Header } = Layout;

const DOMAIN_CARDS = [
  { key: "users_domain", name: "Users Domain", description: "Handles user registration and user master data." },
  { key: "product_domain", name: "Product Domain", description: "Manages product catalog and product master data." },
  { key: "sales_domain", name: "Sales Domain", description: "Owns sales transactions and shop sales activity." },
  { key: "shop_domain", name: "Shop Domain", description: "Manages shop registration, metadata, and mesh participation." },
  { key: "user_preferences_domain", name: "User Preferences Domain", description: "Owns user preferences and personalization data." },
  { key: "engagement_domain", name: "Engagement Domain", description: "Tracks user engagement and interaction events." },
  { key: "interaction_domain", name: "Interaction Domain", description: "Handles user interaction events." },
];

export default function App() {
  const [selected, setSelected] = useState("overview");
  const [activeDomain, setActiveDomain] = useState(null); // Track which domain card is clicked
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  return (
    <Layout className="dm-shell" style={{ minHeight: "100%", height: "100%", width: "100%", overflow: "hidden" }}>
      <Sider
        theme="dark"
        width={220}
        collapsed={sidebarCollapsed}
        collapsedWidth={isMobile ? 0 : 72}
        trigger={null}
        breakpoint="lg"
        onBreakpoint={(broken) => {
          setIsMobile(broken);
          setSidebarCollapsed(broken);
        }}
        style={{ position: "relative", background: "#061a2f", boxShadow: "2px 0 12px rgba(15, 23, 42, 0.25)", display: "flex", flexDirection: "column", minHeight: 0, transition: "all 0.2s ease" }}
      >
        <div style={{ color: "#f8fafc", fontWeight: 700, fontSize: sidebarCollapsed ? 16 : 20, padding: sidebarCollapsed ? "14px 10px" : 18, textAlign: sidebarCollapsed ? "center" : "left", letterSpacing: 0.2, borderBottom: "1px solid rgba(148, 163, 184, 0.2)", lineHeight: 1.25, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {sidebarCollapsed ? "DM" : "Data Mesh Control Plane"}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          inlineCollapsed={sidebarCollapsed && !isMobile}
          selectedKeys={[selected]}
          onClick={e => {
            setSelected(e.key);
            setActiveDomain(null); // Reset detail view when switching tabs
          }}
          style={{ borderRight: 0, fontSize: 14, fontWeight: 500, marginTop: 8, background: "#061a2f", flex: 1, overflowY: "auto", minHeight: 0 }}
          items={[
            { key: "overview", icon: <AppstoreOutlined />, label: "Overview" },
            { key: "domains", icon: <DatabaseOutlined />, label: "Domains" },
            { key: "products", icon: <ShopOutlined />, label: "Data Products" },
            { key: "shop", icon: <ShopOutlined />, label: "Shop Analysis" },
            { key: "pipeline-monitoring", icon: <SafetyOutlined />, label: "Pipeline Monitoring" },
            { key: "domain-analytics", icon: <DatabaseOutlined />, label: "Domain-wise Analytics" },
            { key: "governance", icon: <SafetyOutlined />, label: "Governance" },
            { key: "governance-prioritization", icon: <SafetyOutlined />, label: "Governance Prioritization" },
            { key: "mlhealth", icon: <SafetyOutlined />, label: "ML Health" },
          ]}
        />
        <div style={{ position: "absolute", bottom: 0, width: "100%", color: "#94a3b8", fontSize: 12, textAlign: "center", padding: 14, borderTop: "1px solid rgba(148, 163, 184, 0.2)", opacity: sidebarCollapsed ? 0 : 1, transition: "opacity 0.2s ease", pointerEvents: sidebarCollapsed ? "none" : "auto" }}>
          © {new Date().getFullYear()} Data Mesh Platform
        </div>
      </Sider>
      <Layout style={{ background: "#f5f6fa", minHeight: 0, height: "100%", minWidth: 0, width: "100%", overflow: "hidden" }}>
        <Header style={{ background: "#ffffff", padding: "0 16px", fontSize: 20, fontWeight: 700, color: "#0f172a", borderBottom: "1px solid #e2e8f0", minHeight: 56, display: "flex", alignItems: "center", justifyContent: "space-between", letterSpacing: 0.1, boxShadow: "0 1px 4px rgba(15, 23, 42, 0.06)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
            <button
              type="button"
              onClick={() => setSidebarCollapsed(prev => !prev)}
              style={{
                width: 34,
                height: 34,
                borderRadius: 8,
                border: "1px solid #cbd5e1",
                background: "#fff",
                color: "#0f172a",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "pointer",
                flexShrink: 0,
                padding: 0
              }}
              aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            </button>
            <div style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {selected === "overview" && "Mesh Overview"}
            {selected === "domains" && "Domains & Ownership"}
            {selected === "products" && "Data Products Catalog"}
            {selected === "shop" && "Shop Analysis"}
            {selected === "pipeline-monitoring" && "Pipeline Monitoring"}
            {selected === "governance" && "Governance Control Plane"}
            {selected === "governance-prioritization" && "Governance Prioritization"}
            {selected === "mlhealth" && "ML Health & Anomalies"}
            {selected === "domain-analytics" && "Domain-wise Analytics"}
            </div>
          </div>
        </Header>
        <Content style={{ padding: 16, background: "#f5f6fa", minHeight: 0, minWidth: 0, width: "100%", overflow: "auto" }}>
          {/* Mesh-native content routing */}
          {selected === "overview" && <Home />}
          {selected === "domains" && <Domains />}
          {selected === "products" && <Catalog />}
          {selected === "shop" && <ShopAnalysis />}
          {selected === "pipeline-monitoring" && <PipelineMonitoring />}
          {selected === "governance" && <GovernanceControlPlane />}
          {selected === "governance-prioritization" && <GovernancePrioritization />}
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