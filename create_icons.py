"""Create navigation icons for Libiry."""

from PIL import Image, ImageDraw
from pathlib import Path

def create_back_icon(path: Path, size=48):
    """Create back arrow icon."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw left arrow
    margin = size // 6
    mid = size // 2

    points = [
        (size - margin, margin),      # Top right
        (margin, mid),                 # Left point
        (size - margin, size - margin) # Bottom right
    ]
    draw.polygon(points, fill=(80, 80, 80, 255))

    img.save(path, 'PNG')


def create_plus_icon(path: Path, size=48):
    """Create plus icon."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = size // 6
    thickness = size // 6
    mid = size // 2

    # Horizontal bar
    draw.rectangle([margin, mid - thickness//2, size - margin, mid + thickness//2], fill=(80, 80, 80, 255))
    # Vertical bar
    draw.rectangle([mid - thickness//2, margin, mid + thickness//2, size - margin], fill=(80, 80, 80, 255))

    img.save(path, 'PNG')


def create_minus_icon(path: Path, size=48):
    """Create minus icon."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = size // 6
    thickness = size // 6
    mid = size // 2

    # Horizontal bar only
    draw.rectangle([margin, mid - thickness//2, size - margin, mid + thickness//2], fill=(80, 80, 80, 255))

    img.save(path, 'PNG')


def create_search_icon(path: Path, size=48):
    """Create magnifying glass (search) icon in black."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw circle (lens) - black color
    circle_center = (size // 3, size // 3)
    circle_radius = size // 4
    thickness = max(2, size // 12)

    # Draw circle outline
    draw.ellipse(
        [circle_center[0] - circle_radius, circle_center[1] - circle_radius,
         circle_center[0] + circle_radius, circle_center[1] + circle_radius],
        outline=(0, 0, 0, 255),
        width=thickness
    )

    # Draw handle
    handle_start_x = circle_center[0] + int(circle_radius * 0.7)
    handle_start_y = circle_center[1] + int(circle_radius * 0.7)
    handle_end_x = size - size // 8
    handle_end_y = size - size // 8

    draw.line(
        [(handle_start_x, handle_start_y), (handle_end_x, handle_end_y)],
        fill=(0, 0, 0, 255),
        width=thickness
    )

    img.save(path, 'PNG')

def create_forward_icon(path: Path, size=48):
    """Create forward arrow icon."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw right arrow
    margin = size // 6
    mid = size // 2

    points = [
        (margin, margin),              # Top left
        (size - margin, mid),          # Right point
        (margin, size - margin)        # Bottom left
    ]
    draw.polygon(points, fill=(80, 80, 80, 255))

    img.save(path, 'PNG')

def create_up_icon(path: Path, size=48):
    """Create up arrow icon."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw up arrow
    margin = size // 6
    mid = size // 2

    points = [
        (margin, size - margin),       # Bottom left
        (mid, margin),                 # Top point
        (size - margin, size - margin) # Bottom right
    ]
    draw.polygon(points, fill=(80, 80, 80, 255))

    img.save(path, 'PNG')

def create_refresh_icon(path: Path, size=48):
    """Create refresh/circular arrow icon."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw circular arrow (arc with arrow head)
    margin = size // 6
    thickness = size // 8

    # Draw arc
    bbox = [margin, margin, size - margin, size - margin]
    draw.arc(bbox, start=45, end=315, fill=(80, 80, 80, 255), width=thickness)

    # Draw arrow head at end of arc
    arrow_size = size // 5
    # Arrow pointing clockwise at top-right of arc
    ax = size - margin - arrow_size // 2
    ay = margin + arrow_size
    points = [
        (ax, ay - arrow_size),
        (ax + arrow_size, ay),
        (ax - arrow_size // 2, ay)
    ]
    draw.polygon(points, fill=(80, 80, 80, 255))

    img.save(path, 'PNG')

if __name__ == '__main__':
    # Create icons in resources folder
    resources = Path(__file__).parent / 'resources' / 'icons'
    resources.mkdir(parents=True, exist_ok=True)

    create_back_icon(resources / 'back.png')
    create_forward_icon(resources / 'forward.png')
    create_up_icon(resources / 'up.png')
    create_refresh_icon(resources / 'refresh.png')
    create_plus_icon(resources / 'plus.png')
    create_minus_icon(resources / 'minus.png')
    create_search_icon(resources / 'search.png')

    # Also copy to customize folder
    customize = Path(__file__).parent / 'customize'
    customize.mkdir(parents=True, exist_ok=True)

    create_back_icon(customize / 'back.png')
    create_forward_icon(customize / 'forward.png')
    create_up_icon(customize / 'up.png')
    create_refresh_icon(customize / 'refresh.png')
    create_plus_icon(customize / 'plus.png')
    create_minus_icon(customize / 'minus.png')
    create_search_icon(customize / 'search.png')

    print("Icons created successfully!")
