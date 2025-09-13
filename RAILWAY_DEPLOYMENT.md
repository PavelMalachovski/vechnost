# Railway.com Deployment Guide

This guide will help you deploy the Vechnost Telegram bot to Railway.com.

## Prerequisites

1. **Railway Account**: Sign up at [railway.app](https://railway.app)
2. **GitHub Repository**: Your code should be in a GitHub repository
3. **Telegram Bot Token**: Get one from [@BotFather](https://t.me/BotFather)

## Deployment Steps

### 1. Connect Repository to Railway

1. Log in to your Railway dashboard
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Choose your repository
5. Railway will automatically detect it as a Python project

### 2. Configure Environment Variables

In your Railway project dashboard:

1. Go to the "Variables" tab
2. Add the following environment variables:

```
TELEGRAM_BOT_TOKEN=your_bot_token_here
LOG_LEVEL=INFO
```

**Important**: Replace `your_bot_token_here` with your actual bot token from @BotFather.

### 3. Deploy

1. Railway will automatically start building and deploying
2. Monitor the build logs in the "Deployments" tab
3. The bot will start automatically once deployment is complete

### 4. Verify Deployment

1. Check the deployment logs for any errors
2. Test your bot by sending `/start` command
3. The bot should respond with the theme selection menu

## Configuration Files

The project includes several Railway-specific configuration files:

- `railway.toml`: Railway deployment configuration
- `Procfile`: Alternative deployment method
- `Dockerfile`: Container-based deployment option

## Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | Yes | - |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | No | INFO |
| `PYTHONPATH` | Python path (set automatically) | No | /app |
| `PYTHONUNBUFFERED` | Unbuffered Python output (set automatically) | No | 1 |

## Monitoring and Logs

- **Logs**: View real-time logs in the Railway dashboard
- **Metrics**: Monitor CPU, memory, and network usage
- **Health Checks**: Railway automatically monitors your service

## Troubleshooting

### Common Issues

1. **Healthcheck failures**:
   - The bot includes a health check server on port 8080
   - Railway will check `/health` endpoint to verify the service is running
   - If healthcheck fails, check logs for startup errors

2. **Bot not responding**:
   - Check if `TELEGRAM_BOT_TOKEN` is set correctly
   - Verify the token is valid by testing with @BotFather

3. **Build failures**:
   - Check build logs for dependency issues
   - Ensure all required files are in the repository

4. **Runtime errors**:
   - Check application logs for error messages
   - Verify environment variables are set correctly

### Getting Help

- Check Railway documentation: [docs.railway.app](https://docs.railway.app)
- View application logs in Railway dashboard
- Test locally first: `python -m vechnost_bot`

## Scaling

Railway automatically handles:
- **Auto-scaling**: Based on traffic
- **Health checks**: Automatic restarts on failure
- **Zero-downtime deployments**: Rolling updates

## Security Notes

- Never commit your bot token to the repository
- Use Railway's environment variables for sensitive data
- The bot token is automatically encrypted in Railway

## Cost

Railway offers:
- **Free tier**: $5 credit monthly
- **Pay-as-you-go**: Only pay for what you use
- **No hidden fees**: Transparent pricing

## Next Steps

After successful deployment:

1. **Test thoroughly**: Try all bot features
2. **Monitor usage**: Check Railway metrics
3. **Set up monitoring**: Consider external monitoring tools
4. **Backup**: Regular backups of your data

## Support

For issues with:
- **Railway platform**: Contact Railway support
- **Bot functionality**: Check the application logs
- **Code issues**: Review the test suite and run locally
