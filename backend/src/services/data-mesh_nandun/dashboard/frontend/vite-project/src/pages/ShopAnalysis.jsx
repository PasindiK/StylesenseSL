import React, { useEffect, useState } from "react";
import { Select, Card, Row, Col, Statistic, Spin, Typography, Table, Tag } from "antd";
import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from "recharts";
import axios from "axios";

const { Option } = Select;
const { Title } = Typography;
const BASE = "http://localhost:8000";

const KPI_CONFIG = [
  {
    key: "total_shops",
    title: "Total Shops Registered",
    helper: "All shops onboarded to the mesh",
    color: "#3b82f6",
    status: "info"
  },
  {
    key: "active_shops",
    title: "Active Shops Today",
    helper: "Shops active today",
    color: "#22c55e",
    status: "healthy"
  },
  {
    key: "shops_with_sales_today",
    title: "Shops with Sales Today",
    helper: "Shops reporting sales data today",
    color: "#22c55e",
    status: "healthy"
  },
  {
    key: "missing_sales",
    title: "Shops Missing Sales Data",
    helper: "No sales reported today",
    color: "#f59e42",
    status: "warning"
  },
  {
    key: "stale_updates",
    title: "Stale Shop Updates (>24h)",
    helper: "Not updated in last 24h",
    color: "#ef4444",
    status: "issue"
  }
];

function KpiCard({ title, value, helper, color, status }) {
  const statusColor = status === "healthy" ? "#22c55e" : status === "warning" ? "#f59e42" : status === "issue" ? "#ef4444" : color;
  return (
    <div
      style={{
        width: 240,
        height: 150,
        background: "#fff",
        borderRadius: 16,
        boxShadow: "0 2px 12px #e0e7ef22",
        border: "1px solid #e5e7eb",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: 20,
        margin: 0,
        textAlign: "center",
        transition: "box-shadow 0.2s",
        overflow: "hidden"
      }}
    >
      <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 8, color: "#222" }}>{title}</div>
      <div style={{ fontSize: 32, fontWeight: 700, color: statusColor, marginBottom: 6 }}>
        {value === null || value === undefined ? "N/A" : value}
      </div>
      <div style={{ fontSize: 13, color: "#888" }}>{helper}</div>
    </div>
  );
}

function PipelineStatusCard({ name, status, lastRun, duration, error }) {
  let color = '#888';
  if (status === 'success') color = '#22c55e';
  else if (status === 'failed') color = '#ef4444';
  else if (status === 'delayed') color = '#f59e42';
  return (
    <Card style={{ width: 260, margin: 8, border: `1.5px solid ${color}` }}>
      <div style={{ fontWeight: 700, fontSize: 17, marginBottom: 6 }}>{name}</div>
      <div style={{ fontWeight: 600, color, fontSize: 16, marginBottom: 4 }}>Status: {status}</div>
      <div style={{ fontSize: 14, marginBottom: 2 }}>Last Run: {lastRun ? new Date(lastRun).toLocaleString() : '-'}</div>
      <div style={{ fontSize: 14, marginBottom: 2 }}>Duration: {duration ? duration + 's' : '-'}</div>
      {error && <div style={{ color: '#ef4444', fontSize: 13, marginTop: 4 }}>Error: {error}</div>}
    </Card>
  );
}

function DataProductReadiness({ shopId }) {
  const [readiness, setReadiness] = useState(null);
  useEffect(() => {
    if (!shopId) return;
    // Fetch shop health, contract, ML health, etc.
    Promise.all([
      axios.get(`${BASE}/health`),
      axios.get(`${BASE}/domains/metadata`),
      axios.get(`${BASE}/domain-health/anomalies`)
    ]).then(([healthRes, metaRes, mlRes]) => {
      // Find shop domain info
      const health = healthRes.data["shop_domain"] || {};
      const meta = (metaRes.data || []).find(d => d.domain === "shop");
      const ml = (mlRes.data.domains || []).find(d => d.domain_name === "shop_domain");
      // Data Freshness
      const freshness = health.last_modified ? new Date(health.last_modified) : null;
      // Quality Score (simple: based on nulls and duplicates)
      let quality = "Good";
      if (health.null_counts && Object.values(health.null_counts).some(v => v > 0)) quality = "Warning";
      // Contract Status
      const contractStatus = meta ? meta.contract_status : "Unknown";
      // ML Health
      const mlHealth = ml ? (ml.anomaly_flag === 0 ? "Normal" : "Anomaly") : "Unknown";
      setReadiness({ freshness, quality, contractStatus, mlHealth });
    });
  }, [shopId]);
  if (!readiness) return <Spin />;
  return (
    <Table
      dataSource={[{
        key: 1,
        freshness: readiness.freshness ? `${Math.round((Date.now() - readiness.freshness.getTime())/1000/60/60)}h ago` : "-",
        quality: readiness.quality,
        contractStatus: readiness.contractStatus,
        mlHealth: readiness.mlHealth
      }]}
      columns={[
        { title: "Data Freshness", dataIndex: "freshness", render: v => <Tag color={v === "-" ? "red" : "green"}>{v}</Tag> },
        { title: "Quality Score", dataIndex: "quality", render: v => <Tag color={v === "Good" ? "green" : "orange"}>{v}</Tag> },
        { title: "Contract Status", dataIndex: "contractStatus", render: v => <Tag color={v === "Valid" ? "green" : "red"}>{v}</Tag> },
        { title: "ML Health", dataIndex: "mlHealth", render: v => <Tag color={v === "Normal" ? "green" : v === "Anomaly" ? "red" : "orange"}>{v}</Tag> }
      ]}
      pagination={false}
      style={{ marginTop: 24, marginBottom: 24 }}
    />
  );
}

export default function ShopAnalysis() {
  const [shops, setShops] = useState([]);
  const [selectedShop, setSelectedShop] = useState(null);
  const [shopSales, setShopSales] = useState([]);
  const [loading, setLoading] = useState(false);
  const [shopKPIs, setShopKPIs] = useState({});
  const [trendingProducts, setTrendingProducts] = useState([]);
  const [productMap, setProductMap] = useState({});
  const [overview, setOverview] = useState(null); // Shop overview KPIs
  const [pipelineStatus, setPipelineStatus] = useState(null);

  useEffect(() => {
    axios.get(`${BASE}/shops`).then(res => setShops(res.data || []));
    // Fetch shop overview KPIs
    axios.get(`${BASE}/api/shop-overview`).then(res => setOverview(res.data));
  }, []);

  useEffect(() => {
    // Fetch all products and build a map product_id -> product
    axios.get(`${BASE}/products`).then(res => {
      const arr = res.data.data || res.data;
      const map = {};
      arr.forEach(p => { map[p.product_id] = p; });
      setProductMap(map);
    });
  }, []);

  useEffect(() => {
    if (!selectedShop) return;
    setLoading(true);
    axios.get(`${BASE}/sales?shop_id=${selectedShop}`).then(res => {
      setShopSales(res.data.data || []);
      // Calculate KPIs for the shop
      const sales = res.data.data || [];
      const totalSales = sales.reduce((sum, s) => sum + (s.final_amount || 0), 0);
      const orderCount = sales.length;
      const uniqueUsers = new Set(sales.map(s => s.user_id)).size;
      setShopKPIs({ totalSales, orderCount, uniqueUsers });
      // Calculate trending products (top 3 by total sales, handle ties and missing values)
      const productSales = {};
      sales.forEach(s => {
        if (!s.product_id || !s.final_amount) return;
        if (!productSales[s.product_id]) productSales[s.product_id] = 0;
        productSales[s.product_id] += s.final_amount;
      });
      // Always get top 3, even if some have the same sales
      const trending = Object.entries(productSales)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 3)
        .map(([product_id, amount]) => ({ product_id, amount }));
      setTrendingProducts(trending);
      setLoading(false);
    });
  }, [selectedShop]);

  useEffect(() => {
    // Fetch pipeline status
    axios.get(`${BASE}/pipeline-status`).then(res => setPipelineStatus(res.data));
    // Optionally, poll every 10s for live updates
    const interval = setInterval(() => {
      axios.get(`${BASE}/pipeline-status`).then(res => setPipelineStatus(res.data));
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ padding: 24, maxWidth: 1400, margin: '0 auto' }}>
      <Title level={2} style={{ fontWeight: 700, marginBottom: 32 }}>Shop-wise Data Analysis</Title>
      {/* Pipeline Status Section */}
      <div style={{ marginBottom: 32 }}>
        <Title level={4} style={{ marginBottom: 12 }}>Pipeline/Job Status</Title>
        {pipelineStatus ? (
          <Row gutter={[16, 16]} style={{ flexWrap: 'wrap' }}>
            {Object.entries(pipelineStatus).map(([name, info]) => (
              <Col key={name} xs={24} sm={12} md={8} lg={6} xl={6}>
                <PipelineStatusCard
                  name={name}
                  status={info.status}
                  lastRun={info.last_run}
                  duration={info.duration}
                  error={info.error}
                />
              </Col>
            ))}
          </Row>
        ) : <Spin />}
      </div>
      {/* Shop Overview KPI Cards */}
      {overview ? (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "center",
            gap: "32px",
            marginBottom: "40px"
          }}
        >
          {KPI_CONFIG.map(kpiConf => (
            <KpiCard
              key={kpiConf.key}
              title={kpiConf.title}
              value={overview && overview[kpiConf.key] !== undefined ? overview[kpiConf.key] : null}
              helper={kpiConf.helper}
              color={kpiConf.color}
              status={kpiConf.status}
            />
          ))}
        </div>
      ) : (
        <Spin style={{ marginBottom: 32 }} />
      )}
      <Select
        showSearch
        style={{ width: 300, marginBottom: 24 }}
        placeholder="Select a shop"
        optionFilterProp="children"
        onChange={setSelectedShop}
        filterOption={(input, option) =>
          option.children.toLowerCase().indexOf(input.toLowerCase()) >= 0
        }
      >
        {shops.map(shop => (
          <Option key={shop.shop_id} value={shop.shop_id}>{shop.shop_name || shop.shop_id}</Option>
        ))}
      </Select>
      {loading ? <Spin /> : selectedShop && (
        <>
          <Row gutter={16} style={{ marginBottom: 24 }}>
            <Col span={8}><Card><Statistic title="Total Sales (LKR)" value={shopKPIs.totalSales} /></Card></Col>
            <Col span={8}><Card><Statistic title="Order Count" value={shopKPIs.orderCount} /></Card></Col>
            <Col span={8}><Card><Statistic title="Unique Users" value={shopKPIs.uniqueUsers} /></Card></Col>
          </Row>
          <Card title="Sales Trend">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={shopSales.map(s => ({
                date: s.transaction_date,
                sales: s.final_amount
              }))}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="sales" stroke="#1890ff" />
              </LineChart>
            </ResponsiveContainer>
          </Card>
          <DataProductReadiness shopId={selectedShop} />
          <Card title="AI Insights" style={{ marginTop: 24 }}>
            {trendingProducts.length > 0 ? (
              <>
                <b>Trending Products (by sales):</b>
                <Row gutter={16} style={{ marginTop: 12 }}>
                  {trendingProducts.slice(0, 3).map(tp => {
                    const prod = productMap[tp.product_id];
                    return (
                      <Col span={8} key={tp.product_id}>
                        <Card
                          hoverable
                          cover={prod && prod.product_url && prod.product_url.startsWith('http') ? (
                            <img alt={prod.name} src={prod.product_url} style={{ height: 180, objectFit: 'cover' }} />
                          ) : (
                            <div style={{ height: 180, background: '#eee', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>No Image</div>
                          )}
                        >
                          <Card.Meta
                            title={prod ? prod.name : `Product ${tp.product_id}`}
                            description={prod ? (
                              <>
                                <div>Category: {prod.category}</div>
                                <div>Price: LKR {prod.price_LKR}</div>
                                <div>Sales: {tp.amount}</div>
                              </>
                            ) : <div>Sales: {tp.amount}</div>}
                          />
                        </Card>
                      </Col>
                    );
                  })}
                </Row>
              </>
            ) : (
              <p>No trending products found for this shop.</p>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
