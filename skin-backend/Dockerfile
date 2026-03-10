FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

COPY vskin/package*.json ./
RUN npm install

COPY vskin/ ./

ARG VITE_BASE_PATH=/
ARG VITE_API_BASE=/skinapi
ARG BUILD_MODE=standard
ENV VITE_BASE_PATH=${VITE_BASE_PATH}
ENV VITE_API_BASE=${VITE_API_BASE}
ENV BUILD_MODE=${BUILD_MODE}

RUN if [ "$BUILD_MODE" = "low-memory" ] || [ "$BUILD_MODE" = "fast" ]; then \
			npm run build-fast; \
		else \
			npm run build; \
		fi

FROM python:3.11-slim

WORKDIR /app

COPY skin-backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY skin-backend/ .
COPY --from=frontend-builder /frontend/dist /app/frontend-dist

# 赋予启动脚本执行权限
RUN chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "routes_reference:app", "--host", "0.0.0.0", "--port", "8000"]
