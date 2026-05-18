# Included from root Makefile: include workers/workers.mk
# Publish: make worker-<id>-publish  (export DOCKER_USER=...)

define WORKER_PUBLISH_RULE
.PHONY: worker-$(1)-image worker-$(1)-build-hub worker-$(1)-push worker-$(1)-publish
worker-$(1)-image:
	docker build -t mouthsync-worker-$(1):local ./$(3)

worker-$(1)-build-hub: hub-check
	docker build --platform $$(DOCKER_PLATFORM) \
		-t docker.io/$$(DOCKER_USER)/$(2):$$(DOCKER_TAG) \
		./$(3)
	@echo "[make] Built: docker.io/$$(DOCKER_USER)/$(2):$$(DOCKER_TAG)"

worker-$(1)-push: hub-check
	docker push docker.io/$$(DOCKER_USER)/$(2):$$(DOCKER_TAG)

worker-$(1)-publish: worker-$(1)-build-hub worker-$(1)-push
endef

$(eval $(call WORKER_PUBLISH_RULE,sadtalker,mouthsync-worker-sadtalker,runpod-worker-sadtalker))
$(eval $(call WORKER_PUBLISH_RULE,wav2lip,mouthsync-worker-wav2lip,runpod-worker-wav2lip))

# Aliases (back-compat)
worker-build-hub: worker-sadtalker-build-hub
worker-push: worker-sadtalker-push
worker-publish: worker-sadtalker-publish
worker-image: worker-sadtalker-image

WORKER_READY_PUBLISH := worker-sadtalker-publish worker-wav2lip-publish

worker-publish-ready: $(WORKER_READY_PUBLISH)

worker-list:
	@echo "MouthSync workers (workers/registry.yaml):"
	@echo ""
	@echo "  id              image                              ready   gpu"
	@echo "  sadtalker       mouthsync-worker-sadtalker         yes     yes   (stage 1)"
	@echo "  wav2lip         mouthsync-worker-wav2lip           yes     yes   (stage 2)"
	@echo ""
	@echo "  make worker-<id>-publish"
	@echo "  make worker-publish-ready   # sadtalker + wav2lip"
