# Vercel Deployment Guide

## Prerequisites
1. Install Vercel CLI: `npm install -g vercel`
2. Create a Vercel account at https://vercel.com

## Deployment Steps

### 1. Install Vercel CLI
```powershell
npm install -g vercel
```

### 2. Login to Vercel
```powershell
vercel login
```

### 3. Deploy the Application
```powershell
cd "C:\Users\KUMAR G\Desktop\LIbrary-management"
vercel
```

### 4. Follow the prompts:
- Set up and deploy? **Y**
- Which scope? Select your account
- Link to existing project? **N**
- Project name? **library-management** (or your choice)
- Directory? **./** (default)
- Override settings? **N**

### 5. Production Deployment
```powershell
vercel --prod
```

## Important Notes

### Database Configuration
⚠️ **SQLite won't work on Vercel** (serverless environment)

You need to use a cloud database. Options:

#### Option 1: Supabase (Recommended - Free tier)
1. Create account at https://supabase.com
2. Create new project
3. Get connection string from Settings > Database
4. Add to Vercel environment variables:
   ```
   DATABASE_URL=postgresql://user:pass@host:5432/dbname
   ```

#### Option 2: Neon (PostgreSQL - Free tier)
1. Create account at https://neon.tech
2. Create database
3. Get connection string
4. Add to Vercel environment variables

#### Option 3: PlanetScale (MySQL - Free tier)
1. Create account at https://planetscale.com
2. Create database
3. Get connection string
4. Update requirements.txt with mysql connector
5. Add to Vercel environment variables

### Environment Variables in Vercel
After deployment, add these in Vercel Dashboard:
1. Go to your project > Settings > Environment Variables
2. Add:
   - `FLASK_ENV`: production
   - `SECRET_KEY`: (generate a strong secret key)
   - `DATABASE_URL`: (your database connection string)
   - `MAIL_SERVER`: smtp.gmail.com
   - `MAIL_PORT`: 587
   - `MAIL_USE_TLS`: True
   - `MAIL_USERNAME`: bothackerr03@gmail.com
   - `MAIL_PASSWORD`: zuldbwitrgqczzr
   - `MAIL_DEFAULT_SENDER`: bothackerr03@gmail.com

### Static Files
Vercel automatically handles static files from the `static/` directory.

### File Storage
For book PDFs and images, use:
- **Cloudinary** (Free tier - images)
- **AWS S3** (Pay per use)
- **Vercel Blob Storage**

## Alternative: Use Railway or Render

If Vercel doesn't work well with your Flask app, try:

### Railway (Easier for Flask)
```powershell
npm install -g railway
railway login
railway init
railway up
```

### Render (Better for databases)
1. Go to https://render.com
2. Connect your GitHub repo
3. Create new Web Service
4. Select Python environment
5. Build command: `pip install -r requirements.txt`
6. Start command: `gunicorn app_new:app`

## Commands Summary

```powershell
# Install Vercel CLI (if you have Node.js/npm)
npm install -g vercel

# Login
vercel login

# Deploy to preview
vercel

# Deploy to production
vercel --prod

# Check deployment status
vercel ls

# View logs
vercel logs
```

## Troubleshooting

If deployment fails:
1. Check `vercel logs` for errors
2. Ensure all dependencies are in requirements.txt
3. Verify Python version compatibility
4. Check environment variables are set correctly

## Post-Deployment

Your app will be available at:
- Preview: `https://library-management-xxx.vercel.app`
- Production: `https://library-management.vercel.app` (or your custom domain)

Configure your custom domain in Vercel Dashboard > Domains.
