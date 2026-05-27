# Updating the documentation

The documentation will be automatically rebuilt and deployed upon merge to main on Github.

For local development, you can use the provided docker-compose which monitors the files for
changes and automatically updates as you modify the local files.

You can access the documentation preview by starting the service (see below) and opening
[http://localhost:4000](http://localhost:4000) in your browser.


To start:
```bash
cd docs
docker compose up -d --build
```

To stop:
```bash
cd docs
docker compose down
```

## Adding a new page

The documentation is organized into four top-level sections — **Getting Started**, **Key Concepts**, **Development**, and **CLI Reference** — plus the home page. To add a new page, copy the template file and edit it:

```bash
cp _base.md my_new_page.md
```

The template (`_base.md`) is annotated with comments explaining each front-matter field, including how to place the page in the navigation hierarchy. Because the filename starts with an underscore, Jekyll skips the template itself during site generation.

