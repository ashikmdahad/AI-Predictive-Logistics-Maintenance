import time, random, argparse, json, datetime, urllib.request
def post(api, path, payload):
    req = urllib.request.Request(api + path, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())
def main():
    p = argparse.ArgumentParser()
    p.add_argument('--api', default='http://localhost:8000')
    p.add_argument('--device', type=int, default=1)
    p.add_argument('--rate', type=float, default=1.0)
    args = p.parse_args()
    print(f"Streaming to {args.api} for device {args.device} every {args.rate}s... CTRL+C to stop")
    while True:
        payload = {"device_id": args.device, "timestamp": datetime.datetime.utcnow().isoformat(),
            "vibration": random.gauss(2.2, 0.4), "temperature": random.gauss(58, 7), "current": random.gauss(10, 2),
            "rpm": random.gauss(1500, 100), "load_pct": min(max(random.gauss(65, 15), 0), 100)}
        try: post(args.api, "/readings/", payload); print("Sent", payload)
        except Exception as e: print("Error:", e)
        time.sleep(args.rate)
if __name__ == "__main__": main()
