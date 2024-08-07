import redis

def scan_redis_keys():
    r = redis.Redis(host='localhost', port=6379, db=0)

    print("Scanning Redis database for all keys...")

    for key in r.scan_iter("*"):
        key_str = key.decode('utf-8')
        key_type = r.type(key).decode('utf-8')
        
        print(f"\nKey: {key_str} (Type: {key_type})")
        
        if key_type == 'hash':
            all_fields = r.hgetall(key)
            for field, value in all_fields.items():
                print(f"  {field.decode('utf-8')}: {value.decode('utf-8')}")
        elif key_type == 'list':
            list_items = r.lrange(key, 0, -1)
            for item in list_items:
                print(f"  {item.decode('utf-8')}")
        elif key_type == 'set':
            set_items = r.smembers(key)
            for item in set_items:
                print(f"  {item.decode('utf-8')}")

if __name__ == "__main__":
    scan_redis_keys()