import React, { useEffect, useState } from "react";
import { Card, Row, Col, Typography, Spin } from "antd";
import { fetchOverview } from "../api/api";

const { Title, Paragraph } = Typography;

const DOMAIN_CARDS = [
  { key: "users_domain", name: "Users Domain", description: "Handles user registration and user master data." },
  { key: "product_domain", name: "Product Domain", description: "Manages product catalog and product master data." },
  { key: "sales_domain", name: "Sales Domain", description: "Owns sales transactions and shop sales activity." },
  { key: "shop_domain", name: "Shop Domain", description: "Manages shop registration, metadata, and mesh participation." },
  { key: "user_preferences_domain", name: "User Preferences Domain", description: "Owns user preferences and personalization data." },
  { key: "engagement_domain", name: "Engagement Domain", description: "Tracks user engagement and interaction events." },
  { key: "interaction_domain", name: "Interaction Domain", description: "Handles user interaction events." },
];

const KPI_CONFIG = [
  {
    key: "totalShops",
    title: "Total Shops Registered",
    helper: "All shops onboarded to the mesh",
    color: "#3b82f6",
    status: "info"
  },
  {
    key: "shopsWithSales",
    title: "Shops with Sales Today",
    helper: "Shops reporting sales data today",
    color: "#22c55e",
    status: "healthy"
  },
  {
    key: "missingSales",
    title: "Shops Missing Sales Data",
    helper: "Shops with no sales reported today",
    color: "#f59e42",
    status: "warning"
  },
  {
    key: "staleUpdates",
    title: "Stale Shop Updates (>24h)",
    helper: "Shops not updated in last 24h",
    color: "#ef4444",
    status: "issue"
  }
];

function KpiCard({ title, value, helper, color, status }) {
  const statusColor = status === "healthy" ? "#22c55e" : status === "warning" ? "#f59e42" : status === "issue" ? "#ef4444" : color;
  return (
    <div
      style={{
        width: "100%",
        maxWidth: 260,
        minWidth: 220,
        height: 170,
        background: "#fff",
        borderRadius: 18,
        boxShadow: "0 2px 16px #e0e7ef22",
        border: `1px solid ${statusColor}22`,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
        margin: "0 auto",
        textAlign: "center",
        transition: "box-shadow 0.2s",
        overflow: "hidden"
      }}
    >
      <div style={{ fontWeight: 700, fontSize: 18, marginBottom: 8, color: "#222" }}>{title}</div>
      <div style={{ fontSize: 36, fontWeight: 700, color: statusColor, marginBottom: 6 }}>{value ?? "-"}</div>
      <div style={{ fontSize: 15, color: statusColor, opacity: 0.85 }}>{helper}</div>
    </div>
  );
}

function DomainCard({ name, description }) {
  return (
    <div
      style={{
        width: "100%",
        maxWidth: 260,
        minWidth: 220,
        height: 170,
        background: "#fff",
        borderRadius: 18,
        boxShadow: "0 2px 16px #e0e7ef22",
        border: "1px solid #e5e7eb",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
        margin: "0 auto",
        textAlign: "center",
        transition: "box-shadow 0.2s",
        overflow: "hidden",
        cursor: "pointer"
      }}
    >
      <div style={{ fontWeight: 600, fontSize: 18, marginBottom: 8 }}>{name}</div>
      <div style={{ color: "#666", fontSize: 15 }}>{description}</div>
    </div>
  );
}

export default function ShopDomainAnalytics() {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchMetrics() {
      setLoading(true);
      try {
        const overview = await fetchOverview();
        setMetrics({
          totalShops: overview.totalShops || 0,
          shopsWithSales: overview.shopsWithSales || 0,
          missingSales: overview.missingSales || 0,
          staleUpdates: overview.staleUpdates || 0,
        });
      } catch (e) {
        setMetrics({ totalShops: 0, shopsWithSales: 0, missingSales: 0, staleUpdates: 0 });
      }
      setLoading(false);
    }
    fetchMetrics();
  }, []);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 32 }}>
        <Title level={2} style={{ fontWeight: 700, marginBottom: 0 }}>Shop Domain Health & Participation Analytics</Title>
        <span className="env-badge">Production</span>
      </div>
      <Paragraph type="secondary" style={{ marginBottom: 32, fontSize: 17 }}>
        Data Mesh platform metrics for the <b>Shop Domain</b>. These reflect domain health, mesh participation, and data product readiness—not business KPIs.
      </Paragraph>
      {/* KPI Cards Section */}
      <Row gutter={[24, 24]} justify="start" style={{ marginBottom: 40, flexWrap: "wrap" }}>
        {KPI_CONFIG.map(kpi => (
          <Col xs={24} sm={12} md={6} lg={6} xl={6} key={kpi.key} style={{ display: "flex", justifyContent: "center" }}>
            <KpiCard
              title={kpi.title}
              value={metrics ? metrics[kpi.key] : "-"}
              helper={kpi.helper}
              color={kpi.color}
              status={kpi.status}
            />
          </Col>
        ))}
      </Row>
      {/* Domain cards below */}
      <Row gutter={[24, 24]} justify="start" style={{ marginBottom: 32, flexWrap: "wrap" }}>
        {DOMAIN_CARDS.map(domain => (
          <Col xs={24} sm={12} md={6} lg={6} xl={6} key={domain.key} style={{ display: "flex", justifyContent: "center" }}>
            <DomainCard name={domain.name} description={domain.description} />
          </Col>
        ))}
      </Row>
      {/* Shop domain metrics below */}
      <div className="section">
        {loading ? (
          <Spin size="large" />
        ) : (
          <Row gutter={[32, 32]}>
            {/* ...other metrics or charts can go here... */}
          </Row>
        )}
      </div>
    </div>
  );
}
