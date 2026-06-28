IMAGE_REPO  ?=
IMAGE_PREFIX := $(if $(IMAGE_REPO),$(IMAGE_REPO)/,)
IMAGE_NAME  ?= fd-agent
IMAGE_TAG   ?= latest
NAMESPACE   ?= agentgateway-system
PLATFORMS   ?= linux/amd64,linux/arm64

.PHONY: build push deploy undeploy logs

build: ## Build multi-arch image
	docker buildx build --platform $(PLATFORMS) \
		--load -t $(IMAGE_PREFIX)$(IMAGE_NAME):$(IMAGE_TAG) server/

push: ## Build and push multi-arch image
	docker buildx build --platform $(PLATFORMS) \
		--push \
		-t $(IMAGE_PREFIX)$(IMAGE_NAME):$(IMAGE_TAG) \
		server/

deploy: ## Deploy FD Agent to K8s
	kubectl apply -f config/serviceaccount.yaml
	kubectl apply -f config/service.yaml
	sed 's|image: fd-agent:latest|image: $(IMAGE_PREFIX)$(IMAGE_NAME):$(IMAGE_TAG)|' \
		config/deployment.yaml | kubectl apply -f -
	kubectl rollout status deployment/fd-agent -n $(NAMESPACE) --timeout=60s

undeploy: ## Remove FD Agent from K8s
	kubectl delete -f config/deployment.yaml --ignore-not-found
	kubectl delete -f config/service.yaml --ignore-not-found
	kubectl delete -f config/serviceaccount.yaml --ignore-not-found

logs: ## Tail FD Agent logs
	kubectl logs -n $(NAMESPACE) deploy/fd-agent -f --tail=50
