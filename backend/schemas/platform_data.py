from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class FacebookDataResponse(BaseModel):
    listing_id: Optional[str] = None
    seller_profile_url: Optional[str] = None
    marketplace_category: Optional[str] = None
    item_condition: Optional[str] = None
    delivery_method: Optional[str] = None
    seller_name: Optional[str] = None
    seller_location_city: Optional[str] = None
    seller_location_province: Optional[str] = None
    comments_count: Optional[int] = None
    comments_text: Optional[str] = None
    post_date: Optional[datetime] = None
    image_urls: Optional[str] = None
    image_hashes: Optional[str] = None

class InstagramDataResponse(BaseModel):
    username: Optional[str] = None
    user_id_ig: Optional[str] = None
    hashtags: Optional[str] = None
    likes_count: Optional[int] = None
    comments_count: Optional[int] = None
    followers: Optional[int] = None
    following: Optional[int] = None
    bio_text: Optional[str] = None
    bio_links: Optional[str] = None
    profile_pic_url: Optional[str] = None
    profile_pic_hash: Optional[str] = None
    is_business_account: Optional[bool] = None
    post_type: Optional[str] = None
    post_date: Optional[datetime] = None
    mentioned_accounts: Optional[str] = None
    image_urls: Optional[str] = None
    image_hashes: Optional[str] = None
    caption_full: Optional[str] = None

class TiktokDataResponse(BaseModel):
    username: Optional[str] = None
    user_id_tt: Optional[str] = None
    video_id: Optional[str] = None
    video_views: Optional[int] = None
    likes: Optional[int] = None
    shares: Optional[int] = None
    comments_count: Optional[int] = None
    hashtags: Optional[str] = None
    sounds_used: Optional[str] = None
    bio_text: Optional[str] = None
    bio_links: Optional[str] = None
    profile_pic_url: Optional[str] = None
    profile_pic_hash: Optional[str] = None
    followers: Optional[int] = None
    following: Optional[int] = None
    post_date: Optional[datetime] = None
    mentioned_accounts: Optional[str] = None
    image_urls: Optional[str] = None
    image_hashes: Optional[str] = None
    description_full: Optional[str] = None

class MercadoLibreDataResponse(BaseModel):
    seller_id: Optional[str] = None
    seller_nickname: Optional[str] = None
    seller_reputation_level: Optional[str] = None
    seller_reputation_score: Optional[str] = None
    seller_transactions_completed: Optional[int] = None
    item_id: Optional[str] = None
    item_condition: Optional[str] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    shipping_mode: Optional[str] = None
    available_stock: Optional[int] = None
    sold_quantity: Optional[int] = None
    questions_count: Optional[int] = None
    warranty_text: Optional[str] = None
    official_store_id: Optional[str] = None
    image_urls: Optional[str] = None
    image_hashes: Optional[str] = None
    post_date: Optional[datetime] = None

class PlatformDataPayload(BaseModel):
    facebook: Optional[FacebookDataResponse] = None
    instagram: Optional[InstagramDataResponse] = None
    tiktok: Optional[TiktokDataResponse] = None
    mercadolibre: Optional[MercadoLibreDataResponse] = None
