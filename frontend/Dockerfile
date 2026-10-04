FROM node:lts-alpine AS build
WORKDIR /build
# registry 可配：内网/镜像源构建用 --build-arg NPM_REGISTRY=...（G6/H3）
ARG NPM_REGISTRY=https://registry.npmjs.org
RUN npm config set registry ${NPM_REGISTRY}
# npm ci 严格按 package-lock.json 安装（G6/H3：旧版 npm install 绕过 lock，依赖树不可复现）
COPY package.json package-lock.json ./
RUN npm ci
COPY ./ .
RUN npm run build

FROM nginx
RUN mkdir /app
COPY --from=build /build/dist /app
COPY --from=build /build/nginx.conf /etc/nginx/nginx.conf
EXPOSE 80
