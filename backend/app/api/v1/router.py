from fastapi import APIRouter

from app.api.v1 import (
    admin,
    allocations,
    audit,
    auth,
    domains,
    pools,
    posts,
    proposals,
    signals,
    threads,
    votes,
)

api_router = APIRouter()

api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(domains.router, prefix="/domains", tags=["domains"])
api_router.include_router(threads.router, prefix="/threads", tags=["threads"])
api_router.include_router(posts.router, prefix="/posts", tags=["posts"])
api_router.include_router(signals.router, prefix="/signals", tags=["signals"])
api_router.include_router(proposals.router, prefix="/proposals", tags=["proposals"])
api_router.include_router(votes.router, prefix="/votes", tags=["votes"])
api_router.include_router(pools.router, prefix="/pools", tags=["pools"])
api_router.include_router(allocations.router, prefix="/allocations", tags=["allocations"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
