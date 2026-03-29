FROM python:3.11-slim

WORKDIR /cookies_extractor

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV COOKIES_BROWSER=firefox
ENV COOKIES_BROWSER_PROFILE=/cookies_extractor/firefox_profile
ENV COOKIES_OUTPUT_DIR=/cookies_extractor/cookies

COPY requirements-cookies.txt ./requirements-cookies.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements-cookies.txt

COPY src/cookies_extractor/config.py ./config.py
COPY src/cookies_extractor/extract_youtube_cookies.py ./extract_youtube_cookies.py
COPY src/cookies_extractor/validate_youtube_cookies.py ./validate_youtube_cookies.py
COPY src/cookies_extractor/run_extractor.py ./run_extractor.py

RUN mkdir -p /cookies_extractor/cookies /cookies_extractor/firefox_profile

CMD ["python", "run_extractor.py"]
