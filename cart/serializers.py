from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Sum
from rest_framework import serializers

from product.models import FlightTicket, Hotel, Activity
from product.serializers import FlightTicketSerializer, HotelSerializer, ActivitySerializer
from .models import Cart, CartItem


def get_item_serializer(item):
    # 根据项目的类型返回相应的序列化器
    if isinstance(item, FlightTicket):
        return FlightTicketSerializer
    elif isinstance(item, Hotel):
        return HotelSerializer
    elif isinstance(item, Activity):
        return ActivitySerializer
    # 如果有其他类型的项目，可以在此处添加对应的逻辑
    else:
        raise ValueError(f'Unsupported item type: {type(item)}')


class CartSerializer(serializers.ModelSerializer):
    price = serializers.SerializerMethodField(read_only=True)
    items = serializers.SerializerMethodField(read_only=True)

    def get_price(self, obj):
        total_price = 0
        cart_items = CartItem.objects.filter(cart=obj).select_related('item_content_type').prefetch_related('item')
        for cart_item in cart_items:
            total_price += cart_item.item.price * cart_item.quantity
        return total_price

    def get_items(self, obj):
        cart_items = CartItem.objects.filter(cart=obj).select_related('item_content_type').prefetch_related('item')
        items_data = []
        for cart_item in cart_items:
            try:
                item_instance = cart_item.item
                item_serializer = get_item_serializer(item_instance)
                item_data = item_serializer(item_instance).data
                item_data['cartItemId'] = cart_item.id
                items_data.append(item_data)
            except ObjectDoesNotExist:
                pass
        return items_data

    class Meta:
        model = Cart
        fields = ['price', 'items']