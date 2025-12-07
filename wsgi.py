from app_new import app

# Vercel expects the WSGI app to be named 'app'
# This file serves as the entry point for Vercel
if __name__ == "__main__":
    app.run()
