# Security

rmstrokes turns template, recipe and SVG files into reMarkable documents. Those files are often shared or downloaded,
so building one should never do more than write the document you asked for. It runs on your own computer, with no
server and no network calls. If you find a way to make it do something else, please tell me.

## Reporting

Please report it privately through the repository's **Security** tab (**Report a vulnerability**) rather than in a
public issue. A short description and a file that reproduces it are plenty. I'll reply when I can and fix it in the
next release; only the latest release gets fixes.

## What counts

- a template or recipe file (TOML or JSON) or a template expression that runs code, or reads files outside its
  own folder, or writes anywhere but the output you asked for
- an SVG that makes rmstrokes read other local files or go online
- a generated `.rmdoc` that breaks the tablet or the documents on it

**Python template files and installed template packages are code**: they run with your permissions, like any Python
module. That's why a recipe can only use a `.py` template with `--allow-python`. Only use ones you trust; that part
isn't a vulnerability.
