# SPDX-License-Identifier: GPL-3.0-or-later
"""Pixel level conversion between a downloaded asset and the Paralives maps.

Paralives shades with albedo, normal, occlusion and smoothness, and has no
metallic channel at all. A glTF or GLB from the web arrives with the opposite
convention: roughness rather than smoothness, occlusion packed in the red of
an ORM texture, metalness in the blue. Nothing lines up, so every map has to
be rebuilt rather than copied.

Two rules keep the results faithful:

  * Reads return the bytes that were in the file, never a colour managed
    version of them. For an 8 bit image, which is every PNG an asset ships,
    Image.pixels is already raw whatever the colorspace tag says. Only a float
    buffer is held linear, and that one is encoded back numerically rather
    than by retagging the datablock: assigning to colorspace_settings on a
    generated image throws its pixels away.
  * Maps of different sizes are resampled to the largest of the set, never the
    smallest, so packing an occlusion map into a normal map never throws away
    normal detail.
"""

import os

import numpy as np

import bpy

#: Above this, a rebuild would allocate more than a gigabyte of float32 and
#: stall Blender for seconds. Paralives assets never need it.
MAX_PIXELS = 4096 * 4096

_NON_COLOR = "Non-Color"


# --------------------------------------------------------------------------
# Reading


def _is_srgb(image):
    settings = getattr(image, "colorspace_settings", None)
    return bool(settings) and settings.name in {"sRGB", "Filmic sRGB"}


def linear_to_srgb(values):
    """The transfer curve Blender applies when it loads an sRGB float image."""
    low = values * 12.92
    high = 1.055 * np.power(np.maximum(values, 1e-8), 1.0 / 2.4) - 0.055
    return np.where(values <= 0.0031308, low, high)


def _undo_colour_management(image, array):
    """Put a float buffer back the way the file had it.

    An 8 bit image hands its stored bytes straight back, so there is nothing
    to undo. A float buffer tagged sRGB has been linearised on load, and the
    channel maths here wants the encoded values, not the linear ones.
    """
    if not getattr(image, "is_float", False) or not _is_srgb(image):
        return array
    array[:, :, :3] = np.clip(linear_to_srgb(array[:, :, :3]), 0.0, 1.0)
    return array


def dimensions(image):
    if image is None:
        return (0, 0)
    try:
        width, height = image.size
    except (AttributeError, ValueError):
        return (0, 0)
    return (int(width), int(height))


def too_large(image):
    width, height = dimensions(image)
    return width * height > MAX_PIXELS


def read(image):
    """Whole image as (height, width, 4) float32 in raw file values, or None."""
    width, height = dimensions(image)
    if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
        return None
    flat = np.empty(width * height * 4, dtype=np.float32)
    try:
        image.pixels.foreach_get(flat)
    except (AttributeError, TypeError, RuntimeError):
        try:
            flat = np.array(image.pixels[:], dtype=np.float32)
        except (AttributeError, RuntimeError):
            return None
    if flat.size != width * height * 4:
        return None
    return _undo_colour_management(image, flat.reshape(height, width, 4))


def sample(image, count=1024, seed=7):
    """A scattering of raw RGBA values, cheap even on a 4K texture.

    Reading a 4K image costs 268 MB and a noticeable pause. Identifying what a
    texture *is* only needs a few thousand pixels, so this pokes at the buffer
    instead of copying it.
    """
    width, height = dimensions(image)
    total = width * height
    if total <= 0:
        return None

    if total <= 512 * 512:
        pixels = read(image)
        if pixels is None:
            return None
        flat = pixels.reshape(-1, 4)
        if len(flat) <= count:
            return flat
        step = max(1, len(flat) // count)
        return flat[::step]

    generator = np.random.default_rng(seed)
    indices = generator.integers(0, total, size=count)
    out = np.empty((count, 4), dtype=np.float32)
    try:
        buffer = image.pixels
        for row, index in enumerate(indices):
            start = int(index) * 4
            out[row] = buffer[start:start + 4]
    except (AttributeError, IndexError, RuntimeError):
        return None
    return _undo_colour_management(image, out.reshape(1, count, 4)).reshape(count, 4)


# --------------------------------------------------------------------------
# Statistics used to identify a texture


class Stats:
    """What the pixels alone say about an image."""

    __slots__ = ("mean", "saturation", "is_gray", "looks_like_normal",
                 "alpha_used", "width", "height")

    def __init__(self, mean, saturation, is_gray, looks_like_normal,
                 alpha_used, width, height):
        self.mean = mean
        self.saturation = saturation
        self.is_gray = is_gray
        self.looks_like_normal = looks_like_normal
        self.alpha_used = alpha_used
        self.width = width
        self.height = height


def stats(image):
    values = sample(image)
    width, height = dimensions(image)
    if values is None or not len(values):
        return None

    rgb = values[:, :3]
    mean = tuple(float(v) for v in rgb.mean(axis=0))
    high = rgb.max(axis=1)
    low = rgb.min(axis=1)
    saturation = float(np.mean(high - low))

    # A tangent space normal map sits around (0.5, 0.5, 1.0): blue everywhere,
    # red and green hovering at the midpoint. Nothing else looks like that.
    normalish = (
        mean[2] > 0.75
        and 0.35 < mean[0] < 0.68
        and 0.35 < mean[1] < 0.68
        and float(np.mean(np.abs(rgb[:, 0] - 0.5))) < 0.22
    )

    alpha = values[:, 3]
    alpha_used = bool(np.any(alpha < 0.99))

    return Stats(mean, saturation, saturation < 0.045, normalish, alpha_used,
                 width, height)


# --------------------------------------------------------------------------
# Array helpers


def resample(array, width, height):
    """Nearest neighbour resize. Good enough: these are packing operations."""
    source_height, source_width = array.shape[0], array.shape[1]
    if source_width == width and source_height == height:
        return array
    ys = (np.arange(height) * (source_height / height)).astype(np.int64)
    xs = (np.arange(width) * (source_width / width)).astype(np.int64)
    ys = np.clip(ys, 0, source_height - 1)
    xs = np.clip(xs, 0, source_width - 1)
    return array[ys][:, xs]


def luminance(array):
    """Perceptual gray of an RGBA array, as (height, width)."""
    return (
        0.2126 * array[:, :, 0]
        + 0.7152 * array[:, :, 1]
        + 0.0722 * array[:, :, 2]
    )


def largest_size(arrays):
    width = max((a.shape[1] for a in arrays if a is not None), default=0)
    height = max((a.shape[0] for a in arrays if a is not None), default=0)
    return width, height


def solid(width, height, rgba):
    out = np.empty((height, width, 4), dtype=np.float32)
    out[:, :, 0] = rgba[0]
    out[:, :, 1] = rgba[1]
    out[:, :, 2] = rgba[2]
    out[:, :, 3] = rgba[3] if len(rgba) > 3 else 1.0
    return out


# --------------------------------------------------------------------------
# The Paralives maps


def build_normal_occlusion(normal=None, occlusion=None, occlusion_channel=0):
    """RGB from the normal map, alpha from the occlusion map.

    Either input may be missing. A normal map without occlusion gets a fully
    lit alpha, an occlusion map without a normal map gets a flat normal, which
    is exactly how the game expects an AO only asset to arrive.
    """
    from . import spec

    if normal is None and occlusion is None:
        return None

    width, height = largest_size([normal, occlusion])
    if width <= 0 or height <= 0:
        return None

    if normal is not None:
        out = resample(normal, width, height).copy()
    else:
        out = solid(width, height, spec.FLAT_NORMAL + (1.0,))

    if occlusion is not None:
        ao = resample(occlusion, width, height)
        out[:, :, 3] = ao[:, :, occlusion_channel]
    else:
        out[:, :, 3] = spec.DEFAULT_OCCLUSION
    return np.clip(out, 0.0, 1.0)


def build_smoothness(roughness=None, roughness_channel=1, invert=True,
                     metallic=None, metallic_channel=2):
    """White is reflective, so glTF roughness has to be turned inside out.

    Paralives has no metallic map. A metal that is merely dropped reads as
    flat plastic, so metalness is folded in as extra shine, which keeps a
    chrome or brass part looking like metal instead of grey paint.
    """
    from . import spec

    if roughness is None and metallic is None:
        return None

    width, height = largest_size([roughness, metallic])
    if width <= 0 or height <= 0:
        return None

    if roughness is not None:
        source = resample(roughness, width, height)
        gray = source[:, :, roughness_channel].astype(np.float32)
        value = 1.0 - gray if invert else gray
    else:
        value = np.full((height, width), 0.5, dtype=np.float32)

    if metallic is not None:
        metal = resample(metallic, width, height)[:, :, metallic_channel]
        value = value + metal * spec.METALLIC_SMOOTHNESS_BOOST

    value = np.clip(value, 0.0, 1.0)
    out = np.empty((height, width, 4), dtype=np.float32)
    out[:, :, 0] = value
    out[:, :, 1] = value
    out[:, :, 2] = value
    out[:, :, 3] = 1.0
    return out


def build_detail(base_color, emission=None, emission_strength=1.0):
    """The albedo, kept exactly as it is, with any glow added back on top.

    Paralives has no emission channel. Dropping an emissive map turns a lit
    screen or a neon sign into a dead grey panel, so it is added to the colour
    instead: not physically the same thing, visually much closer.
    """
    if base_color is None:
        return None
    out = base_color.copy()
    if emission is not None:
        glow = resample(emission, out.shape[1], out.shape[0])
        out[:, :, :3] = np.clip(
            out[:, :, :3] + glow[:, :, :3] * float(emission_strength), 0.0, 1.0
        )
    out[:, :, 3] = 1.0
    return out


def build_gray_mask(base_color, keep_contrast=1.0):
    """Desaturate the albedo and recentre it on the 50% gray the game expects.

    GrayMask is a recolouring layer: the swatch supplies the hue, the texture
    supplies only the light and shade. An albedo straight off a download is
    saturated and rarely centred, so it is turned to luminance and shifted so
    its average lands on the neutral tone.
    """
    if base_color is None:
        return None
    gray = luminance(base_color)
    mean = float(gray.mean())
    if mean > 1e-4:
        gray = gray + (0.5 - mean)
    if keep_contrast != 1.0:
        gray = 0.5 + (gray - 0.5) * float(keep_contrast)
    gray = np.clip(gray, 0.0, 1.0)

    out = np.empty(base_color.shape, dtype=np.float32)
    out[:, :, 0] = gray
    out[:, :, 1] = gray
    out[:, :, 2] = gray
    out[:, :, 3] = 1.0
    return out


# --------------------------------------------------------------------------
# Writing


def write_png(array, path, name_hint="ParaForgeTemp"):
    """Write an RGBA float array to a PNG, byte for byte as given."""
    height, width = array.shape[0], array.shape[1]
    image = bpy.data.images.new(
        name_hint, width=width, height=height, alpha=True, float_buffer=False,
        is_data=True,
    )
    try:
        # is_data already tags it Non-Color. Assigning again would regenerate
        # the buffer, which is exactly what must not happen after it is
        # filled, so the tag is only touched when it is actually wrong.
        settings = image.colorspace_settings
        if settings.name != _NON_COLOR:
            try:
                settings.name = _NON_COLOR
            except TypeError:
                pass
        image.pixels.foreach_set(
            np.clip(array, 0.0, 1.0).astype(np.float32).reshape(-1)
        )
        image.file_format = "PNG"
        image.save(filepath=path)
    finally:
        bpy.data.images.remove(image)
    return path


def copy_as_png(image, path):
    """Copy an image to a PNG without touching a single pixel where possible."""
    source = source_path(image)
    if source and source.lower().endswith(".png"):
        if os.path.abspath(source) != os.path.abspath(path):
            with open(source, "rb") as handle:
                data = handle.read()
            with open(path, "wb") as handle:
                handle.write(data)
        return path

    previous_format = image.file_format
    try:
        image.file_format = "PNG"
        image.save(filepath=path)
    except TypeError:
        previous_raw = image.filepath_raw
        try:
            image.filepath_raw = path
            image.save()
        finally:
            image.filepath_raw = previous_raw
    finally:
        image.file_format = previous_format
    return path


def source_path(image):
    """Absolute path on disk, or an empty string for packed images."""
    resolver = getattr(image, "filepath_from_user", None)
    if callable(resolver):
        try:
            resolved = image.filepath_from_user()
        except (RuntimeError, ValueError):
            resolved = ""
    else:
        resolved = getattr(image, "filepath", "") or ""
        if resolved.startswith("//"):
            resolved = ""
    if resolved and os.path.isfile(resolved):
        return os.path.abspath(resolved)
    return ""
