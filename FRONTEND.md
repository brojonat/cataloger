# Frontend Documentation

## Overview

Cataloger includes a simple web UI for viewing database catalogs. The frontend uses:
- **Jinja2** templates for server-side rendering
- **htmx** for dynamic interactions without JavaScript frameworks
- **Static HTML** with progressive enhancement
- **Responsive CSS** for mobile and desktop

## Pages

### Home Page (`/`)

Entry point with:
- Search form to find catalogs by prefix
- Quick access to view latest or timelapse
- About section and quick links

**Usage:**
```
http://localhost:8000/
```

### Current View (`/database/current?prefix=<prefix>`)

Shows the most recent catalog for a database:
- Tabs for different files (catalog.html, summary.html, scripts)
- Dynamic content loading via htmx
- No page refresh needed

**Example:**
```
http://localhost:8000/database/current?prefix=customer-123/orders
```

**What it shows:**
- Latest timestamp for the prefix
- All catalog files for that timestamp
- Tabbed interface to switch between files

### Timelapse View (`/database/timelapse?prefix=<prefix>`)

Historical view of all catalogs over time:
- Timeline of all timestamps (newest first)
- Click timestamp to load catalog files
- Click file to view content
- All via htmx (no page reloads)

**Example:**
```
http://localhost:8000/database/timelapse?prefix=customer-123/orders
```

**What it shows:**
- List of all timestamps (up to 50)
- Files available for selected timestamp
- Content viewer for selected file

## API Endpoints

### HTML Endpoints (for browsers)

```
GET /                                    Home page
GET /database/current?prefix=<prefix>   Latest catalog
GET /database/timelapse?prefix=<prefix> All catalogs over time
```

### API Endpoints (for htmx)

```
GET /api/catalog/content?prefix=<prefix>&timestamp=<ts>&filename=<file>
    Returns: HTML fragment with catalog content

GET /api/catalog/list?prefix=<prefix>&timestamp=<ts>
    Returns: HTML fragment with list of catalog files
```

### Existing API Endpoints

```
POST /catalog             Generate new catalog (requires JWT)
GET  /healthz            Health check
GET  /whoami             Auth test
GET  /metrics            Prometheus metrics
```

## htmx Features Used

### 1. Dynamic Loading

Load content without page refresh:

```html
<div hx-get="/api/catalog/content?..."
     hx-trigger="load"
     hx-swap="innerHTML">
    Loading...
</div>
```

### 2. Click Handlers

```html
<button hx-get="/api/catalog/list?..."
        hx-target="#catalog-list"
        hx-swap="innerHTML">
    Select Timestamp
</button>
```

### 3. Form Submission

```html
<form hx-get="/database/current"
      hx-target="#result">
    <input name="prefix" />
    <button type="submit">View</button>
</form>
```

## Styling

### CSS Variables

```css
:root {
    --primary: #2563eb;
    --secondary: #64748b;
    --background: #f8fafc;
    --surface: #ffffff;
    --border: #e2e8f0;
}
```

### Key Components

- **Cards**: `.card` - Content containers
- **Buttons**: `.button`, `.button.secondary`
- **Tabs**: `.tab`, `.tab.active`
- **Timeline**: `.timeline-item`, `.timeline-item.active`
- **Forms**: `.form-group`, `input`, `label`

### Responsive Design

Breakpoint at 768px:
- Timeline switches to single column
- Button groups stack vertically
- Header becomes vertical

## Development

### Local Development

```bash
# Start server with reload
make run-server

# Or manually
uv run uvicorn server.main:app --reload --host 0.0.0.0 --port 8000
```

Visit: `http://localhost:8000`

### File Structure

```
server/
├── main.py              # FastAPI app with template config
├── templates/
│   ├── base.html        # Base template with header/footer
│   ├── index.html       # Home page
│   ├── current.html     # Latest catalog view
│   ├── timelapse.html   # Historical view
│   ├── error.html       # Error page
│   ├── catalog_list_fragment.html      # htmx fragment
│   └── catalog_content_fragment.html   # htmx fragment
└── static/
    └── style.css        # All styles
```

### Adding New Pages

1. Create template in `server/templates/`:

```html
{% extends "base.html" %}

{% block title %}My Page{% endblock %}

{% block content %}
<h2>My Content</h2>
{% endblock %}
```

2. Add route in `server/main.py`:

```python
@app.get("/my-page", response_class=HTMLResponse, tags=["ui"])
async def my_page(request: Request):
    return templates.TemplateResponse(
        "my_page.html",
        {"request": request, "data": "value"}
    )
```

### Adding htmx Interactions

1. Create API endpoint that returns HTML fragment:

```python
@app.get("/api/my-data", tags=["api"])
async def my_data(request: Request):
    data = fetch_data()
    return templates.TemplateResponse(
        "my_fragment.html",
        {"request": request, "data": data}
    )
```

2. Create fragment template:

```html
<div class="my-component">
    {{ data }}
</div>
```

3. Use in page:

```html
<div hx-get="/api/my-data"
     hx-trigger="load"
     hx-target="this"
     hx-swap="innerHTML">
    Loading...
</div>
```

## Security

### No Authentication on UI

The frontend pages (`/`, `/database/current`, `/database/timelapse`) are **public**.

This is intentional:
- Read-only views of existing catalogs
- No ability to modify or delete data
- Write operations (`POST /catalog`) require JWT

### Embedding Catalog HTML

Catalog content is rendered with `{{ content|safe }}`:
- Catalogs are agent-generated HTML
- Assumed to be safe (agents use trusted code)
- If accepting external HTML, add sanitization

## Performance

### htmx Benefits

- Smaller page loads (only fetch what changed)
- No JavaScript bundle to download
- Faster interactions (no framework overhead)
- Works without JavaScript (degrades gracefully)

### Caching

Consider adding HTTP caching headers:

```python
@app.get("/database/current")
async def database_current(request: Request, prefix: str):
    response = templates.TemplateResponse(...)
    response.headers["Cache-Control"] = "public, max-age=300"
    return response
```

### S3 Performance

- S3 list operations are cached by boto3
- Consider CloudFront for catalog HTML if traffic is high
- Use S3 Transfer Acceleration for large catalogs

## Troubleshooting

### Templates Not Found

```
jinja2.exceptions.TemplateNotFound: index.html
```

**Fix**: Check `BASE_DIR` path in `server/main.py`:

```python
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
```

### Static Files 404

```
GET /static/style.css 404
```

**Fix**: Ensure directory exists and is mounted:

```python
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
```

### htmx Not Loading

Check browser console. If you see:
```
Failed to load resource: https://unpkg.com/htmx.org@1.9.10
```

**Fix**: Download htmx locally or use a CDN that works in your network.

### S3 Storage Not Initialized

```
503 Service Unavailable: S3 storage not initialized
```

**Fix**: Check environment variables:

```bash
export S3_BUCKET=your-bucket-name
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
```

## Future Enhancements

### Real-time Updates

Add WebSocket support to push new catalogs:

```html
<div hx-ws="connect:/ws/updates">
    <div hx-ws="send">Subscribe to customer-123/orders</div>
</div>
```

### Search

Add full-text search across catalogs:

```python
@app.get("/search")
async def search(q: str):
    # Search S3 objects, return matches
    ...
```

### Comparison View

Compare two catalogs side-by-side:

```
GET /database/compare?prefix=<prefix>&t1=<ts1>&t2=<ts2>
```

### Download

Add download buttons for HTML and scripts:

```html
<a href="/api/catalog/download?..." download>
    Download catalog.html
</a>
```

## Summary

The frontend provides a simple, fast UI for viewing catalogs:
- Server-rendered HTML with Jinja2
- Dynamic interactions with htmx
- No JavaScript frameworks needed
- Mobile-responsive design
- Reads from S3, no database required

Visit `http://localhost:8000` to try it!
