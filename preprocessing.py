# Note: This script is used to preprocess images for OCR.
# It is for testing purposes only and should not be used in the final application.
# The final application uses the preprocess_image function from app/helpers.py.

import cv2 as cv
import numpy as np

# Preprocess image for OCR
def preprocess_image(img):
    # Read image as grayscale
    cv_img = cv.imread(img, 0)

    # Apply GaussianBlur to reduce noise
    blur = cv.GaussianBlur(cv_img, (5, 5), 0)

    # Apply Canny edge detection
    edged_no_thresh = cv.Canny(blur, 100, 200)

    # Apply dilation operations
    kernel = np.ones((3,3),np.uint8) # Adjust kernel size if needed
    dilated_img = cv.dilate(edged_no_thresh, kernel, iterations = 1)

    # Invert the colors of dialated image
    inverted_img = cv.bitwise_not(dilated_img)

    # Otsu thresholding
    ret4,thresh_otsu_dilated_inverted = cv.threshold(inverted_img,0,255,cv.THRESH_BINARY+cv.THRESH_OTSU)

    cv.imshow("thresh_otsu_dilated_inverted", thresh_otsu_dilated_inverted)

    cv.waitKey(0)
    cv.imwrite('receipt53_otsu_dilated_inverted.jpg', thresh_otsu_dilated_inverted)
    return thresh_otsu_dilated_inverted


# Preprocess image for OCR using CLAHE (not used in the final application)
def preprocess_image_clahe(img):
    # Read image as grayscale
    cv_img = cv.imread(img, 0)
    
    # Apply CLAHE (Experiment with clipLimit and tileGridSize)
    clahe = cv.createCLAHE()
    img_clahe = clahe.apply(cv_img)


    # Apply Gaussian Blur to reduce noise
    blur = cv.GaussianBlur(cv_img, (5, 5), 0)

    # Apply Canny edge detection
    # edged = cv.Canny(blur, 100, 200) 
    edged_lower = cv.Canny(blur, 100, 180) 
    edged_middle = cv.Canny(blur, 120, 180) 
    edged_upper = cv.Canny(blur, 120, 200)
    edged = cv.Canny(blur, 100, 200)


    # Apply morphological opening (Experiment with kernel size)
    kernel = np.ones((4,4), np.uint8) 
    # eroded_2 = cv.erode(edged, np.ones((2,2), np.uint8), iterations = 1)
    dilated_2x2 = cv.dilate(edged, np.ones((2,2), np.uint8), iterations = 1)
    dilated_3x3 = cv.dilate(edged, np.ones((3,3), np.uint8), iterations = 1)
    dilated_4x4 = cv.dilate(edged, kernel, iterations = 1)
    dilated_5x5 = cv.dilate(edged, np.ones((5,5), np.uint8), iterations = 1)
    # opening = cv.morphologyEx(edged, cv.MORPH_OPEN, kernel)

    # Invert the colors 
    inverted_2x2 = cv.bitwise_not(dilated_2x2)
    inverted_3x3 = cv.bitwise_not(dilated_3x3)
    inverted_4x4 = cv.bitwise_not(dilated_4x4)
    inverted_5x5 = cv.bitwise_not(dilated_5x5)

    # Otsu thresholding
    _, thresh_otsu_2x2 = cv.threshold(inverted_2x2, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU)
    _, thresh_otsu_3x3 = cv.threshold(inverted_3x3, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU)
    _, thresh_otsu_4x4 = cv.threshold(inverted_4x4, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU)
    _, thresh_otsu_5x5 = cv.threshold(inverted_5x5, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU)

    # Optional: Sharpening (Experiment with kernel and amount)
    kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
    sharpened_2x2 = cv.filter2D(thresh_otsu_2x2, -1, kernel)
    sharpened_3x3 = cv.filter2D(thresh_otsu_3x3, -1, kernel)
    sharpened_4x4 = cv.filter2D(thresh_otsu_4x4, -1, kernel)
    sharpened_5x5 = cv.filter2D(thresh_otsu_5x5, -1, kernel)

    
    # display otsu thresholded images
    cv.imshow("thresh_otsu_2x2", thresh_otsu_2x2)
    cv.imshow("thresh_otsu_3x3", thresh_otsu_3x3)
    cv.imshow("thresh_otsu_4x4", thresh_otsu_4x4)
    cv.imshow("thresh_otsu_5x5", thresh_otsu_5x5)
    cv.waitKey(0)
    cv.imwrite('receipt_40_thresh_otsu_2x2.jpg', thresh_otsu_2x2)
    cv.imwrite('receipt_40_thresh_otsu_3x3.jpg', thresh_otsu_3x3)
    cv.imwrite('receipt_40_thresh_otsu_4x4.jpg', thresh_otsu_4x4)
    cv.imwrite('receipt_40_thresh_otsu_5x5.jpg', thresh_otsu_5x5)
    cv.imwrite('receipt_40_sharpened_2x2.jpg', sharpened_2x2)
    cv.imwrite('receipt_40_sharpened_3x3.jpg', sharpened_3x3)
    cv.imwrite('receipt_40_sharpened_4x4.jpg', sharpened_4x4)
    cv.imwrite('receipt_40_sharpened_5x5.jpg', sharpened_5x5)
    return edged  # or thresh_otsu if sharpening is not needed

preprocess_image('receipt53.JPG')
# preprocess_image_clahe('receipt40.JPG')
