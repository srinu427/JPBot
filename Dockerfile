FROM python:3.8-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
	nscd libopus0\
	&& rm -rf /var/lib/apt/lists/*

ENV PATH="/usr/include:$PATH"

ADD jpbot.py /
ADD req.txt /
ADD ffmpeg-linux/ffmpeg /usr/local/bin
RUN pip install -r /req.txt
CMD ["python", "/jpbot.py"]