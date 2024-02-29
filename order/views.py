import json
from collections import defaultdict

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from rest_framework.decorators import api_view

from order.constant import OrderStatus
from order.models import UserOrder, AgentOrder
from order.mq.mq_sender import send_auto_order_cancel
from product.models import CustomPackage
from user.models import User
from utils.number_util import generate_random_number, calculate_price_taxed
import logging

logger = logging.getLogger(__name__)


@api_view(["POST"])
def payment_order(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            order_number = data.get('order_number')
            card_number = data.get('card_number')
            security_code = data.get('security_code')
            amount = data.get('amount')

            user_order = UserOrder.objects.filter(order_number=order_number,
                                                  status=OrderStatus.PENDING_PAYMENT.value).first()
            if not user_order:
                logger.info("order need not payment handle,order:" + order_number)
                return JsonResponse({'result': False,
                                     'errorMsg': 'Order does not exist or the order has already been paid."'},
                                    status=400)
            agent_orders = AgentOrder.objects.filter(user_order=user_order)
            with transaction.atomic():
                user_order.soft_delete()
                for agent_order in agent_orders:
                    agent_order.soft_delete()
                logger.info("order expire handled,order:" + order_number)

            if order_number is None or card_number is None or security_code is None:
                return JsonResponse({'result': False, 'message': 'Invalid JSON format. Missing required fields.'},
                                    status=400)

            return JsonResponse({'result': True, 'message': 'Order placed successfully.'})
        except json.JSONDecodeError:
            return JsonResponse({'result': False, 'errorMsg': 'Invalid JSON format.'}, status=400)
        except Exception as e:
            return JsonResponse({'result': False, 'errorMsg': str(e)}, status=500)
    else:
        return JsonResponse({'result': False, 'errorMsg': 'Only POST requests are allowed.'}, status=405)


# Create your views here.
@api_view(["POST"])
def place_order(request):
    try:
        with transaction.atomic():
            data = json.loads(request.body.decode('utf-8'))
            departure_date = data.get('departure_date')
            end_date = data.get('end_date')
            email = data.get('email')
            phone = data.get('phone')
            package_id = data.get('package_id')
            user = request.user
            try:
                package = CustomPackage.objects.prefetch_related('packageitem_set').get(id=package_id)
            except CustomPackage.DoesNotExist:
                return JsonResponse({'result': False, 'errorMsg': 'Package not found'}, status=404)
            item_map = defaultdict(list)
            agent_map = defaultdict(User)
            current_time = timezone.now()

            # get Item
            package_items = package.packageitem_set.all()
            order_detail = []
            for packageItem in package_items:
                item = packageItem.item
                user_id = item.owner.id
                item_map[user_id].append(item)
                agent_map[user_id] = item.owner
                order_detail.append(packageItem.detail)
            user_order_price = calculate_price_taxed(package.price)
            user_order_number = generate_random_number()
            user_order = UserOrder.objects.create(
                name=package.name,
                order_number=user_order_number,
                order_details=order_detail,
                description=package.description,
                departure_date=departure_date,
                end_date=end_date,
                price=user_order_price,
                user=user,
                phone=phone,
                email=email,
                status=OrderStatus.PENDING_PAYMENT.value  #
            )

            loop_count = 0
            # Adjust agent order information based on whether it is a user-built package.
            for user_id, items in item_map.items():
                loop_count += 1
                package_name = package.name if not package.is_user else 'User-created package'
                package_price_original = package.price if not package.is_user else sum(item.price for item in items)
                package_price_taxed = calculate_price_taxed(package_price_original)
                description = package.description if not package.is_user else 'User-created package'
                agent_order = AgentOrder.objects.create(
                    user_order=user_order,
                    name=package_name,
                    order_number=user_order_number,
                    agent_order_number=str(user_order_number) + str(loop_count),
                    order_details=order_detail,
                    description=description,
                    departure_date=departure_date,
                    end_date=end_date,
                    price=package_price_taxed,
                    user=user,
                    agent=agent_map.get(user_id, None),
                    phone=phone,
                    email=email,
                    status=OrderStatus.PENDING_PAYMENT.value  #
                )
            data = {
                'order_number': user_order.order_number,
                'order_time': str(user_order.create_time)
            }
            json_string = json.dumps(data)
            print(json_string)
            send_auto_order_cancel(json_string)
            logger.info("generate and order,order_number:" + user_order_number)
        return JsonResponse(
            {'result': True, 'data': {'order_number': user_order_number}, 'message': 'Order placed successfully'},
            status=201)

    except Exception as e:
        return JsonResponse({'result': False, 'errorMsg': 'system error'}, status=404)
