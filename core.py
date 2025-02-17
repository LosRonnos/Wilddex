import torch
import os
import openai
import torchvision.transforms as transforms
from torchvision import models
from PIL import Image
import json
import urllib.request

openai.api_key = os.environ.get("OPENAI_API_KEY")

# Load a pre-trained ResNet50 model
model = models.resnet50(pretrained=True)
model.eval()  # Set the model to evaluation mode

# Download the ImageNet class index mapping for human-readable labels
url = "https://s3.amazonaws.com/deep-learning-models/image-models/imagenet_class_index.json"
with urllib.request.urlopen(url) as response:
    imagenet_class_index = json.load(response)

def classify_image_pytorch(image_path):
    preprocess = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225]
        )
    ])
    img = Image.open(image_path)
    img_t = preprocess(img)
    batch_t = torch.unsqueeze(img_t, 0)
    with torch.no_grad():
        out = model(batch_t)
    _, index = torch.max(out, 1)
    idx = str(index.item())
    label = imagenet_class_index[idx][1]
    return label

def generate_species_stats_with_chatgpt(species):
    prompt = (
        f"Provide a factual summary of typical statistics for the species '{species}', including average lifespan, typical size, and average weightin metric units. "
        "Return your answer in two parts separated by a line that contains only '###'. The first part should be a JSON object with keys 'Average Lifespan', 'Typical Size', and 'Average Weight'. "
        "The second part should be a brief textual summary."
    )
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=200
    )
    return response.choices[0].message.content
