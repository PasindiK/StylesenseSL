# Team guide: deploy Stylesense backends on Azure + Vercel env

Share this with the **three** members who own **Agentic**, **Data fabric**, and **Data architecture** VMs.  
**Data mesh** is already deployed separately (same steps apply if someone redoes it).

**Security**

- Do **not** paste Docker Hub or Neo4j passwords into group chats or Git. Share secrets via a password manager or short-lived tokens.
- Prefer a Docker Hub [access token](https://docs.docker.com/security/for-developers/access-tokens/) instead of the account password for `docker login`.
- If a password was ever pasted in chat, **change it** on Docker Hub.

---

## 0. What each person runs

| Role | Who | Image on Docker Hub | Host port | Inbound NSG (TCP) |
|------|-----|---------------------|-----------|-------------------|
| **Agentic** (+ Neo4j) | Member 1 | `YOUR_NAMESPACE/stylesense-agentic` | **8000** | **8000** |
| **Data fabric** | Member 2 | `YOUR_NAMESPACE/stylesense-data-fabric` | **8002** | **8002** |
| **Data architecture** | Member 3 | `YOUR_NAMESPACE/stylesense-data-architecture` | **8003** | **8003** |

Replace **`YOUR_NAMESPACE`** with your team’s Docker Hub **username or organization** (the part before `/` in `namespace/stylesense-agentic:latest`).  
Pull works if the images are **public**; if they are **private**, each member runs `docker login` once.

---

## 1. Azure VM (all members — same steps)

1. Portal → **Virtual machines** → **Create** → **Azure virtual machine**.
2. **Subscription:** Azure for Students (or assigned sub).
3. **Resource group:** Create new (e.g. `rg-stylesense-agentic`).
4. **Region:** Only regions allowed by your school policy (e.g. **Central India**, **Southeast Asia**, **East Asia**, **Malaysia West**, **Austria East**). **Do not** pick US/Europe/Australia unless policy allows.
5. **VM name:** e.g. `stylesense-agentic-vm`.
6. **Image:** Ubuntu Server 22.04 or 24.04 LTS, **x64**.
7. **Size:** e.g. **Standard B2as v2** or **B2ms** (Agentic + Neo4j and Fabric need **more RAM**; Architecture can be smaller).
8. **Authentication:** SSH public key — paste your **`~/.ssh/id_ed25519.pub`** (or generate with `ssh-keygen`).
9. **Inbound ports:** enable **SSH (22)**. You will add the service port (**8000** / **8002** / **8003**) in **Networking** after create (see §4).
10. **Disks:** default OK.
11. **Networking:** note the **Network security group** name; you will edit it after deployment.
12. **Review + create** → **Create**.

After deployment: copy the VM **Public IP** and confirm status **Running**.

---

## 2. SSH from your laptop

```bash
chmod 400 /path/to/your-key.pem
ssh -i /path/to/your-key.pem azureuser@YOUR_PUBLIC_IP
```

---

## 3. Install Docker on the VM

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker $USER
```

Log out and SSH again **or** use `sudo docker` for the next commands.

Verify:

```bash
sudo docker run hello-world
```

---

## 4. Network Security Group (NSG) — critical

Portal → your **VM** → **Networking** → open the **Network security group** → **Inbound security rules** → **Add**:

- **Priority:** e.g. **310** (must be **above** “DenyAllInBound” 65500).
- **Name:** e.g. `allow-api-8000` (use your real port).
- **Source:** Any (or **Internet**).
- **Source port ranges:** **`*`** (asterisk).
- **Destination:** Any.
- **Destination port ranges:** **8000** or **8002** or **8003** (only your role’s port).
- **Protocol:** **TCP**.
- **Action:** Allow.

Save. **Do not** set “source port” to the same number as the app port unless you know you need it — use **\***.

Test from your laptop (replace IP and port):

```bash
nc -zv YOUR_PUBLIC_IP YOUR_PORT
```

---

## 5. Pull images (private repos only)

If images are **private**:

```bash
docker login
# Username: your Docker Hub username (or email if Hub accepts it)
# Password: use an access token from hub.docker.com → Account Settings → Security
```

Then pulls use your namespace as below.

---

## 6. Member 1 — Agentic + Neo4j (port 8000)

Run **Neo4j** and **Agentic** on the **same Docker network** (Neo4j is not exposed to the internet).

Pick one password and use it in **both** places, e.g. `REPLACE_WITH_STRONG_PASSWORD`.

```bash
export NS=YOUR_NAMESPACE
export NEO4J_PASSWORD='REPLACE_WITH_STRONG_PASSWORD'

sudo docker network create stylesense-net 2>/dev/null || true

sudo docker run -d --name neo4j --network stylesense-net --restart unless-stopped \
  -e NEO4J_AUTH=neo4j/$NEO4J_PASSWORD \
  -v neo4j_data:/data \
  neo4j:5

# Wait ~30–60s for Neo4j; then:
sudo docker run -d --name agentic --network stylesense-net --restart unless-stopped -p 8000:8000 \
  -e NEO4J_URI=bolt://neo4j:7687 \
  -e NEO4J_USER=neo4j \
  -e NEO4J_PASSWORD=$NEO4J_PASSWORD \
  -e NEO4J_DB=neo4j \
  -e KG_ENABLED=true \
  -e GEMINI_API_KEY= \
  ${NS}/stylesense-agentic:latest
```

Check:

```bash
sudo docker ps
sudo docker logs agentic --tail 40
curl -s http://127.0.0.1:8000/api/health
```

From laptop:

```bash
curl -s http://YOUR_PUBLIC_IP:8000/api/health
```

**Team lead:** send **`VITE_API_URL`** base as `http://<Member1_PUBLIC_IP>:8000/api`.

---

## 7. Member 2 — Data fabric (port 8002)

```bash
export NS=YOUR_NAMESPACE

sudo docker pull ${NS}/stylesense-data-fabric:latest
sudo docker run -d --name data-fabric --restart unless-stopped -p 8002:8002 \
  ${NS}/stylesense-data-fabric:latest
```

Check:

```bash
curl -s http://127.0.0.1:8002/api/health/ping
```

From laptop (path may vary if health route differs):

```bash
curl -s http://YOUR_PUBLIC_IP:8002/api/health/ping
```

**Vercel:** set **`VITE_DATA_FABRIC_API_URL`** to match frontend calls — often `http://<Member2_IP>:8002` or `http://<Member2_IP>:8002/api` (confirm in DevTools when something 404s).

---

## 8. Member 3 — Data architecture (port 8003)

```bash
export NS=YOUR_NAMESPACE

sudo docker pull ${NS}/stylesense-data-architecture:latest
sudo docker run -d --name data-arch --restart unless-stopped -p 8003:8003 \
  ${NS}/stylesense-data-architecture:latest
```

Check:

```bash
curl -s http://127.0.0.1:8003/api/health
```

From laptop:

```bash
curl -s http://YOUR_PUBLIC_IP:8003/api/health
```

**Vercel:** **`VITE_DATA_ARCH_API_URL`** = `http://<Member3_PUBLIC_IP>:8003/api`

---

## 9. Vercel — frontend (HTTPS, no mixed content)

Browsers **block** `https://your-app.vercel.app` from calling **`http://`** Azure APIs (“mixed content”).

Use **`frontend/vercel.json`** rewrites: the UI calls same-origin **`/re/agentic/...`**, **`/re/mesh/...`**, etc., and Vercel proxies to your VMs server-side. Update **`frontend/vercel.json`** with the team’s public IPs when they change, commit, and redeploy.

In Vercel → **Settings** → **Environment Variables** (Production), set values from **`frontend/.env.vercel.example`**:

| Variable | Value (example) |
|----------|-----------------|
| `VITE_API_URL` | `/re/agentic` |
| `VITE_AGENTIC_API_URL` | `/re/agentic` |
| `VITE_DATA_MESH_API_URL` | `/re/mesh` |
| `VITE_DATA_FABRIC_API_URL` | `/re/fabric` |
| `VITE_DATA_ARCH_API_URL` | `/re/arch` |

Then **Redeploy**. Ensure the Vercel project **Root Directory** is **`frontend`** (or move `vercel.json` accordingly).

---

## 10. Troubleshooting

| Problem | What to try |
|---------|-------------|
| `nc` / `curl` timeout from laptop | NSG: destination port, **source port** `*`, VM **Running**, correct **public IP**. |
| `permission denied` for Docker | `sudo docker` or log out/in after `usermod -aG docker`. |
| Agentic exits / Neo4j errors | Same `NEO4J_PASSWORD` in Neo4j and agentic; wait for Neo4j before starting agentic; `docker logs neo4j`. |
| Pull denied | `docker login`; image name must match **`YOUR_NAMESPACE`**. |

---

## 11. Credits / cleanup

**Stop** or **delete** the resource group when the demo is over so billing stops.
