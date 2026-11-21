"""rmstrokes: reMarkable documents with a PDF background and movable pen strokes.

SVG/vector shapes to pen strokes (hatch fill, outlines, one compact cluster per object), the
layer API and .rmdoc writer, tokens, write-in fields, parameter schemas, templates as data,
recipes and the intro page.
"""
__version__ = "0.1.1"  # x-release-please-version

from .devices import DEVICES, Device, device_key, get_device
from .fields import FieldStyle, WriteIn, draw_write_in
from .geometry import FitError, Rect, grid_cells
from .intro import IntroSpec, intro_page, token_maker
from .layers import Document, DocumentResult, Layer, Page
from .params import Param, Schema, SchemaError
from .pdf import Painter, draw_strokes
from .recipe import Recipe, Section, build_document, build_recipe, load_recipe
from .templates import Context, Template, available_templates, get_template, register
from .tokens import NameTag, Placement, Token, TokenArt, token_art
from .vectorize import Stroke

__all__ = ["DEVICES", "Device", "device_key", "get_device", "FieldStyle", "WriteIn", "draw_write_in",
           "FitError", "Rect", "grid_cells", "IntroSpec", "intro_page", "token_maker", "Document",
           "DocumentResult", "Layer", "Page",
           "Param", "Schema", "SchemaError", "Painter", "draw_strokes", "Recipe", "Section", "build_document",
           "build_recipe", "load_recipe", "Context", "Template", "available_templates", "get_template",
           "register", "NameTag", "Placement", "Token", "TokenArt", "token_art", "Stroke"]
