# How to Add Redis to Railway

## Quick Setup (30 seconds)

1. **Open Railway Dashboard**
   - Go to https://railway.app
   - Select your `vechnost` project

2. **Add Redis Database**
   - Click **"+ New"** button
   - Select **"Database"**
   - Choose **"Add Redis"**

3. **Automatic Configuration**
   Railway will automatically:
   - ✅ Create a Redis instance
   - ✅ Set `REDIS_URL` environment variable for your bot service
   - ✅ Trigger a redeploy with Redis connected

4. **Verify Connection**
   Watch deployment logs for:
   ```
   ✅ using_external_redis_url url=redis://default:...
   ✅ external_redis_configured
   ✅ Application created with handlers
   ```

## Redis URL Format

Railway will set:
```
REDIS_URL=redis://default:password@red-xxxxx.railway.app:6379
```

Your bot's code will automatically:
- Detect this URL
- Skip local Redis startup
- Connect to Railway Redis
- Persist user sessions across restarts

## Cost

- **Free** on Railway's free tier
- Includes 512 MB RAM (more than enough for your bot)

## Benefits

✅ User sessions persist across restarts
✅ Payment status maintained
✅ Game progress saved
✅ Better performance
✅ Production-ready

## Alternative: External Redis Provider

If you prefer an external provider:

### Upstash (Free Tier)
1. Go to https://upstash.com
2. Create Redis database
3. Copy connection URL
4. Add to Railway environment variables:
   ```
   REDIS_URL=redis://default:password@your-host.upstash.io:6379
   ```

### Redis Cloud (Free 30MB)
1. Go to https://redis.com/try-free/
2. Create free database
3. Copy connection URL
4. Add to Railway environment variables

