"""
Simplified integrated app that combines features
"""
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI(title="Lightning Integrated Dashboard")

# Setup templates - use a simple HTML response for now
@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Lightning Integrated Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .container { max-width: 1200px; margin: 0 auto; }
            .header { background: #f0f0f0; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
            .services { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
            .service { background: white; border: 1px solid #ddd; padding: 20px; border-radius: 8px; }
            .service h3 { margin-top: 0; color: #333; }
            .status { padding: 5px 10px; border-radius: 4px; display: inline-block; }
            .status.running { background: #d4edda; color: #155724; }
            .status.stopped { background: #f8d7da; color: #721c24; }
            a { color: #007bff; text-decoration: none; }
            a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Lightning Integrated Dashboard</h1>
                <p>Access all Lightning services from one place</p>
            </div>
            
            <div class="services">
                <div class="service">
                    <h3>Lightning API</h3>
                    <p><span class="status running">Running</span></p>
                    <p>Core API for all Lightning operations</p>
                    <p><a href="http://localhost:8000" target="_blank">Open API →</a></p>
                    <p><a href="http://localhost:8000/docs" target="_blank">API Documentation →</a></p>
                </div>
                
                <div class="service">
                    <h3>Chat Interface</h3>
                    <p><span class="status running">Running</span></p>
                    <p>Interactive chat with Lightning AI</p>
                    <p><a href="http://localhost:8501" target="_blank">Open Chat →</a></p>
                </div>
                
                <div class="service">
                    <h3>Dashboard</h3>
                    <p><span class="status running">Running</span></p>
                    <p>Task management and monitoring</p>
                    <p><a href="http://localhost:8502" target="_blank">Open Dashboard →</a></p>
                </div>
                
                <div class="service">
                    <h3>Context Hub</h3>
                    <p><span class="status running">Running</span></p>
                    <p>Persistent storage and search</p>
                    <p>API: <code>http://localhost:3000</code></p>
                </div>
                
                <div class="service">
                    <h3>RabbitMQ</h3>
                    <p><span class="status running">Running</span></p>
                    <p>Message queue management</p>
                    <p><a href="http://localhost:15672" target="_blank">Management UI →</a></p>
                    <p>User: <code>lightning</code> Pass: <code>lightning123</code></p>
                </div>
                
                <div class="service">
                    <h3>Event Processor</h3>
                    <p><span class="status running">Running</span></p>
                    <p>Processing events in real-time</p>
                    <p>Connected to Redis event bus</p>
                </div>
            </div>
            
            <div style="margin-top: 40px; padding: 20px; background: #f8f9fa; border-radius: 8px;">
                <h3>Quick Links</h3>
                <ul>
                    <li><a href="/settings">Settings</a> - Configure providers and API keys</li>
                    <li><a href="/events">Events</a> - View real-time event stream</li>
                    <li><a href="/health">Health Check</a> - System status</li>
                </ul>
            </div>
        </div>
    </body>
    </html>
    """

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "integrated-app"}

@app.get("/settings", response_class=HTMLResponse)
async def settings():
    return """
    <html>
    <head><title>Settings</title></head>
    <body>
        <h1>Settings</h1>
        <p>Settings page coming soon...</p>
        <p><a href="/">← Back to Dashboard</a></p>
    </body>
    </html>
    """

@app.get("/events", response_class=HTMLResponse)
async def events():
    return """
    <html>
    <head><title>Events</title></head>
    <body>
        <h1>Event Stream</h1>
        <p>Real-time events coming soon...</p>
        <p><a href="/">← Back to Dashboard</a></p>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)