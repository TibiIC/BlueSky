# Hosting on Vultr

One Ubuntu 24.04 server runs the whole app:

| Part | How it runs |
|---|---|
| Web app (globe, Dev tab, API) | `node build` (SvelteKit adapter-node) as the `bluesky-app` service, port 3000, local only |
| TERRA live weather | `python3 server.py` as the `bluesky-terra` service, port 8765, local only |
| Front door | Caddy: HTTPS (free certificate for `IP-WITH-DASHES.sslip.io`) and a site password |
| Database | MongoDB Atlas (unchanged); the server's IP must be on Atlas's IP Access List |

## First time

1. Create a Vultr server: Cloud Compute (shared CPU), Stockholm, Ubuntu 24.04, 2 vCPU / 4 GB, with the
   public key from `~/.ssh/bluesky_vultr.pub` under *SSH Keys*.
2. Add the server's IP to MongoDB Atlas → Network Access → IP Access List.
3. From the repository root:

```sh
ssh -i ~/.ssh/bluesky_vultr root@SERVER_IP 'bash -s' < deploy/setup.sh   # once: Node 22, Caddy, firewall
deploy/deploy.sh SERVER_IP                                                # build, upload, start
```

The site is at `https://SERVER-IP-WITH-DASHES.sslip.io` (user `bluesky`, password in `deploy/.secrets`,
created on the first deploy and never committed).

The Climate Lens data (`frontend/static/data/lens/`) is committed, so a fresh clone deploys as is.
After the Apetit data changes, rebuild it with `python3 lens/build_data.py` and commit.

## Every update

```sh
deploy/deploy.sh SERVER_IP
```

To refresh the data after decisions in the Dev tab, run the pipeline locally as usual
(`python3 -m quality.pipeline && python3 -m quality.publish_mongo`); the hosted app reads MongoDB, so it
shows the new run on reload without a redeploy.

## Look at the server

```sh
ssh -i ~/.ssh/bluesky_vultr root@SERVER_IP
systemctl status bluesky-app bluesky-terra caddy
journalctl -u bluesky-app -n 50
```
