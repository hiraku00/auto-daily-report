import Quartz
import Vision
from Cocoa import NSURL, NSData, NSImage
import CoreFoundation

def capture_screen_to_image():
    """
    Captures the main screen and returns a CGImage.
    """
    # Main display ID
    display_id = Quartz.CGMainDisplayID()
    
    # Capture the screen
    image_ref = Quartz.CGDisplayCreateImage(display_id)
    return image_ref

def recognize_text(image_ref):
    """
    Recognizes text in the given CGImage using Vision Framework.
    """
    if image_ref is None:
        return ""

    text_request = Vision.VNRecognizeTextRequest.alloc().init()
    text_request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    text_request.setUsesLanguageCorrection_(True)
    text_request.setRecognitionLanguages_(["ja-JP", "en-US"]) # Prioritize Japanese and English

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image_ref, None)
    
    success, error = handler.performRequests_error_([text_request], None)
    
    if not success:
        print(f"Error executing text recognition: {error}")
        return ""
    
    results = text_request.results()
    extracted_text = []
    
    for observation in results:
        # Get the top candidate for each recognized string
        candidate = observation.topCandidates_(1)[0]
        extracted_text.append(candidate.string())
        
    return "\n".join(extracted_text)

def get_screen_text():
    """
    Captures the screen and returns the recognized text.
    """
    image_ref = capture_screen_to_image()
    if image_ref:
        return recognize_text(image_ref)
    return ""
