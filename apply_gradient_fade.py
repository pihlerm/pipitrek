import numpy as np
from PIL import Image

def apply_vertical_gradient_fade(input_path, output_path, width=6000, height=560, top_fade_end=100, bottom_fade_start=459):
    """
    Apply a vertical gradient fade to black at the top and bottom edges of an image.
    
    Args:
        input_path (str): Path to input PNG image.
        output_path (str): Path to save output PNG image.
        width (int): Expected image width (6000 pixels).
        height (int): Expected image height (563 pixels).
        top_fade_end (int): Row where top fade ends (100).
        bottom_fade_start (int): Row where bottom fade starts (462).
    """
    # Load image
    try:
        img = Image.open(input_path).convert('RGBA')
    except Exception as e:
        raise ValueError(f"Failed to load image: {e}")

    # Validate dimensions
    if img.size != (width, height):
        raise ValueError(f"Expected image size {width}x{height}, got {img.size[0]}x{img.size[1]}")

    # Get image data as numpy array
    img_array = np.array(img)

    # Create alpha mask
    alpha = np.ones((height, width), dtype=np.uint8) * 255  # Default: fully opaque

    # Top fade (rows 0 to 99)
    for y in range(top_fade_end):
        # Linear fade: 0 (black) at y=0 to 255 (full image) at y=100
        alpha_value = int(255 * (y / (top_fade_end - 1)))
        alpha[y, :] = alpha_value

    # Middle (rows 100 to 462): no change (alpha = 255)

    # Bottom fade (rows 463 to 562)
    for y in range(bottom_fade_start, height):
        # Linear fade: 255 (full image) at y=462 to 0 (black) at y=562
        alpha_value = int(255 * ((height - 1 - y) / (height - 1 - bottom_fade_start)))
        alpha[y, :] = alpha_value

    # Apply alpha mask to image
    img_array[:, :, 3] = alpha  # Set alpha channel

    # Create output image
    output_img = Image.fromarray(img_array, 'RGBA')

    # Save output
    try:
        output_img.save(output_path, 'PNG')
        print(f"Saved faded image to {output_path}")
    except Exception as e:
        raise ValueError(f"Failed to save image: {e}")


def apply_vertical_gradient_fade_to_black(input_path, output_path, width=6000, height=560, top_fade_end=100, bottom_fade_start=459):
    """
    Apply a vertical gradient fade to solid black at the top and bottom edges of an image and save as JPEG.
    
    Args:
        input_path (str): Path to input PNG image.
        output_path (str): Path to save output JPEG image.
        width (int): Expected image width (6000 pixels).
        height (int): Expected image height (563 pixels).
        top_fade_end (int): Row where top fade ends (100).
        bottom_fade_start (int): Row where bottom fade starts (462).
    """
    # Load image and convert to RGB
    try:
        img = Image.open(input_path).convert('RGB')
    except Exception as e:
        raise ValueError(f"Failed to load image: {e}")

    # Validate dimensions
    if img.size != (width, height):
        raise ValueError(f"Expected image size {width}x{height}, got {img.size[0]}x{img.size[1]}")

    # Get image data as numpy array
    img_array = np.array(img, dtype=np.float32)

    # Create gradient mask
    mask = np.ones((height, width), dtype=np.float32) * 255  # Default: full image

    # Top fade (rows 0 to 99)
    for y in range(top_fade_end):
        # Linear fade: 0 (black) at y=0 to 255 (full image) at y=100
        mask_value = 255 * (y / (top_fade_end - 1))
        mask[y, :] = mask_value

    # Middle (rows 100 to 462): no change (mask = 255)

    # Bottom fade (rows 463 to 562)
    for y in range(bottom_fade_start, height):
        # Linear fade: 255 (full image) at y=462 to 0 (black) at y=562
        mask_value = 255 * ((height - 1 - y) / (height - 1 - bottom_fade_start))
        mask[y, :] = mask_value

    # Apply gradient: blend with black (0, 0, 0)
    black = np.zeros_like(img_array)  # Black image (0, 0, 0)
    mask_3d = mask[:, :, np.newaxis] / 255  # Normalize and broadcast to 3 channels
    faded_array = img_array * mask_3d + black * (1 - mask_3d)

    # Convert back to uint8
    faded_array = np.clip(faded_array, 0, 255).astype(np.uint8)

    # Create output image
    output_img = Image.fromarray(faded_array, 'RGB')

    # Save as JPEG
    try:
        output_img.save(output_path, 'JPEG', quality=95)
        print(f"Saved faded image to {output_path}")
    except Exception as e:
        raise ValueError(f"Failed to save image: {e}")

if __name__ == "__main__":
    input_image = "static/astroImages/MW1.png"
    output_image = "static/astroImages/MW1_faded.png"
    output_image2 = "static/astroImages/MW1_faded_black.png"
    try:
        apply_vertical_gradient_fade(input_image, output_image)
        apply_vertical_gradient_fade_to_black(input_image, output_image2)
    except Exception as e:
        print(f"Error: {e}")