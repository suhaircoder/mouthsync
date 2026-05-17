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

$(eval $(call WORKER_PUBLISH_RULE,lite,mouthsync-worker,runpod-worker))
$(eval $(call WORKER_PUBLISH_RULE,sadtalker,mouthsync-worker-sadtalker,runpod-worker-sadtalker))
$(eval $(call WORKER_PUBLISH_RULE,wav2lip,mouthsync-worker-wav2lip,runpod-worker-wav2lip))
$(eval $(call WORKER_PUBLISH_RULE,musetalk,mouthsync-worker-musetalk,runpod-worker-musetalk))
$(eval $(call WORKER_PUBLISH_RULE,liveportrait,mouthsync-worker-liveportrait,runpod-worker-liveportrait))
$(eval $(call WORKER_PUBLISH_RULE,ultralight,mouthsync-worker-ultralight,runpod-worker-ultralight))
$(eval $(call WORKER_PUBLISH_RULE,livetalking,mouthsync-worker-livetalking,runpod-worker-livetalking))

# Aliases (back-compat → lite)
worker-build-hub: worker-lite-build-hub
worker-push: worker-lite-push
worker-publish: worker-lite-publish
worker-image: worker-lite-image

WORKER_READY_PUBLISH := worker-lite-publish worker-sadtalker-publish worker-wav2lip-publish

worker-publish-ready: $(WORKER_READY_PUBLISH)

worker-list:
	@echo "MouthSync workers (workers/registry.yaml):"
	@echo ""
	@echo "  id              image                              ready   gpu"
	@echo "  lite            mouthsync-worker                   yes     no"
	@echo "  sadtalker       mouthsync-worker-sadtalker         yes     yes"
	@echo "  wav2lip         mouthsync-worker-wav2lip           yes     yes"
	@echo "  musetalk        mouthsync-worker-musetalk          scaffold yes"
	@echo "  liveportrait    mouthsync-worker-liveportrait      scaffold yes"
	@echo "  ultralight      mouthsync-worker-ultralight        scaffold no"
	@echo "  livetalking     mouthsync-worker-livetalking       scaffold yes"
	@echo ""
	@echo "  make worker-<id>-publish"
	@echo "  make worker-publish-ready   # lite + sadtalker + wav2lip"
