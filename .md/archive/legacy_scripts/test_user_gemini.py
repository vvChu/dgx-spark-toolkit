import google.generativeai as genai

genai.configure(
    api_key="sk-9a13a60d641a42f9a74b18d58d44a358",
    transport='rest',
    client_options={'api_endpoint': 'http://100.79.241.120:8045'}
)

model = genai.GenerativeModel('gemini-3-flash')
response = model.generate_content("Hello")
print(response.text)
