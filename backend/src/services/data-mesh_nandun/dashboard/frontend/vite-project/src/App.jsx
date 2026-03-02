import React, { useState, useEffect } from "react";
import { Layout, Menu, Row, Col, Card } from "antd";
import {
  AppstoreOutlined,
  DatabaseOutlined,
  ShopOutlined,
  SafetyOutlined
} from "@ant-design/icons";
import { useNavigate } from 'react-router-dom';
import Home from "./pages/Home";
import Domains from "./pages/Domains";
import ShopAnalysis from "./pages/ShopAnalysis";
import Health from "./pages/Health";
import Catalog from "./pages/Catalog";
import DomainHealthDashboard from "./components/DomainHealthDashboard";

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

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider
        theme="dark"
        width={240}
        style={{ position: "fixed", left: 0, top: 0, bottom: 0, zIndex: 10, boxShadow: "2px 0 8px #e0e7ef22" }}
      >
        <div style={{ color: "#fff", fontWeight: "bold", fontSize: 24, padding: 28, textAlign: "center", letterSpacing: 1, borderBottom: "1px solid #222" }}>
          Data Mesh Control Plane
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selected]}
          onClick={e => {
            setSelected(e.key);
            setActiveDomain(null); // Reset detail view when switching tabs
          }}
          style={{ borderRight: 0, fontSize: 17, fontWeight: 500, marginTop: 8 }}
          items={[
            { key: "overview", icon: <AppstoreOutlined />, label: "Overview" },
            { key: "domains", icon: <DatabaseOutlined />, label: "Domains" },
            { key: "products", icon: <ShopOutlined />, label: "Data Products" },
            { key: "shop", icon: <ShopOutlined style={{ color: '#f59e42' }} />, label: <span style={{ color: '#f59e42', fontWeight: 600 }}>Shop Analysis</span> },
            { key: "domain-analytics", icon: <DatabaseOutlined style={{ color: '#a855f7' }} />, label: <span style={{ color: '#a855f7', fontWeight: 600 }}>Domain-wise Analytics</span> },
            { key: "governance", icon: <SafetyOutlined />, label: "Governance" },
            { key: "mlhealth", icon: <SafetyOutlined style={{ color: '#3b82f6' }} />, label: <span style={{ color: '#3b82f6', fontWeight: 600 }}>ML Health</span> },
          ]}
        />
        <div style={{ position: "absolute", bottom: 0, width: "100%", color: "#aaa", fontSize: 13, textAlign: "center", padding: 16, borderTop: "1px solid #222" }}>
          © {new Date().getFullYear()} Data Mesh Platform
        </div>
      </Sider>
      <Layout style={{ marginLeft: 240, background: "#f5f6fa", minHeight: "100vh", minWidth: "calc(100vw - 240px)" }}>
        <Header style={{ background: "#fff", padding: "0 40px", fontSize: 26, fontWeight: 700, borderBottom: "1px solid #eee", minHeight: 70, display: "flex", alignItems: "center", letterSpacing: 1, boxShadow: "0 2px 8px #e0e7ef11" }}>
          {selected === "overview" && "Mesh Overview"}
          {selected === "domains" && "Domains & Ownership"}
          {selected === "products" && "Data Products Catalog"}
          {selected === "shop" && <span style={{ color: '#f59e42' }}>Shop Analysis</span>}
          {selected === "governance" && "Federated Governance"}
          {selected === "mlhealth" && <span style={{ color: '#3b82f6' }}>ML Health & Anomalies</span>}
          {selected === "domain-analytics" && "Domain-wise Analytics"}
        </Header>
        <Content style={{ padding: 48, background: "#f5f6fa", minHeight: "calc(100vh - 70px)", width: "100%" }}>
          {/* Mesh-native content routing */}
          {selected === "overview" && <Home />}
          {selected === "domains" && <Domains />}
          {selected === "products" && <Catalog />}
          {selected === "shop" && <ShopAnalysis />}
          {selected === "governance" && <Health />}
          {selected === "mlhealth" && (
            <div style={{ maxWidth: 1200, margin: "0 auto", background: "#fff", borderRadius: 16, boxShadow: "0 2px 16px #e0e7ef33", padding: "2.5rem 2rem" }}>
              <DomainHealthDashboard />
            </div>
          )}
          {selected === "domain-analytics" && (
            <div>
              <h1 style={{ fontWeight: 700, fontSize: 32, marginBottom: 32 }}>Domain-wise Analytics</h1>
              {!activeDomain ? (
                <Row gutter={[32, 32]}>
                  {DOMAIN_CARDS.map(domain => (
                    <Col xs={24} sm={12} md={8} lg={6} key={domain.key}>
                      <Card
                        hoverable
                        style={{ borderRadius: 16, minHeight: 170, boxShadow: "0 2px 12px #e0e7ef22", cursor: "pointer" }}
                        onClick={() => setActiveDomain(domain)}
                        bodyStyle={{ padding: 24 }}
                      >
                        <div style={{ fontWeight: 600, fontSize: 20, marginBottom: 10 }}>{domain.name}</div>
                        <div style={{ color: "#666", fontSize: 15 }}>{domain.description}</div>
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
    fetch(`http://localhost:8000/api/domain-metrics/${domain.key}`)
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