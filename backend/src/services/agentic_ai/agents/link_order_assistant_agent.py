"""Guided order assistant for real-world product links.

This agent enforces a fixed, human-confirmed workflow and never places orders
or collects card details in chat.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, unquote
from uuid import uuid4


class LinkOrderAssistantAgent:
    """Stateful guided assistant for placing order requests from product links."""

    SESSION_TIMEOUT_SECONDS = 15 * 60
    COMMON_STORES = ["Daraz", "Amazon", "eBay", "AliExpress", "ikman.lk", "Other"]

    def __init__(self, order_agent: Any):
        self.order_agent = order_agent
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def process_message(
        self,
        session_id: Optional[str],
        text: Optional[str],
        user_id: Optional[str] = None,
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._cleanup_stale_sessions()

        if not session_id or session_id not in self.sessions:
            new_session_id = self._create_session(user_id=user_id, user_profile=user_profile)
            return {
                "session_id": new_session_id,
                "state": "await_start_confirmation",
                "reply": "Hi! Do you want to place an order from a product link? (yes/no)",
                "requires_input": True,
            }

        session = self.sessions[session_id]
        if user_id and not session.get("user_id"):
            session["user_id"] = user_id
        if user_profile:
            merged_profile = dict(session.get("profile") or {})
            for key in ["user_id", "name", "email", "phone", "shipping_address"]:
                if user_profile.get(key) is not None:
                    merged_profile[key] = user_profile.get(key)
            session["profile"] = merged_profile
        session["updated_at"] = time.time()

        user_text = (text or "").strip()
        if not user_text:
            return {
                "session_id": session_id,
                "state": session["state"],
                "reply": self._prompt_for_state(session),
                "requires_input": True,
            }

        lower_text = user_text.lower()
        if lower_text in {"cancel", "stop"}:
            session["state"] = "canceled"
            return {
                "session_id": session_id,
                "state": "canceled",
                "reply": "Order canceled. Let me know if you'd like to try again.",
                "completed": True,
            }

        state = session["state"]

        if state == "await_start_confirmation":
            return self._handle_start_confirmation(session_id, user_text)

        if state == "await_product_link":
            return self._handle_product_link(session_id, user_text)

        if state in {
            "await_manual_name",
            "await_manual_price",
            "await_manual_options",
            "await_manual_store",
        }:
            return self._handle_manual_product_fields(session_id, user_text)

        if state == "await_product_confirmation":
            return self._handle_product_confirmation(session_id, user_text)

        if state == "await_quantity":
            return self._handle_quantity(session_id, user_text)

        if state == "await_variant":
            return self._handle_variant(session_id, user_text)

        if state == "await_color":
            return self._handle_color(session_id, user_text)

        if state == "await_summary_confirmation":
            return self._handle_summary_confirmation(session_id, user_text)

        if state == "await_checkout_action":
            return self._handle_checkout_action(session_id, user_text)

        if state == "await_profile_confirmation":
            return self._handle_profile_confirmation(session_id, user_text)

        if state == "await_edit_choice":
            return self._handle_edit_choice(session_id, user_text)

        if state == "await_payment_method":
            return self._handle_payment_method(session_id, user_text)

        if state == "await_payment_completion":
            return self._handle_payment_completion(session_id, user_text)

        if state == "await_final_confirmation":
            return self._handle_final_confirmation(session_id, user_text)

        if state == "await_order_placed_confirmation":
            return self._handle_order_placed_confirmation(session_id, user_text)

        if state == "await_another_url_decision":
            return self._handle_another_url_decision(session_id, user_text)

        if state in {"completed", "canceled"}:
            return {
                "session_id": session_id,
                "state": state,
                "reply": "This order flow is closed. Start a new one if you want to place another order.",
                "completed": True,
            }

        session["state"] = "await_start_confirmation"
        return {
            "session_id": session_id,
            "state": "await_start_confirmation",
            "reply": "Hi! Do you want to place an order from a product link? (yes/no)",
            "requires_input": True,
        }

    def _create_session(self, user_id: Optional[str], user_profile: Optional[Dict[str, Any]]) -> str:
        session_id = str(uuid4())
        self.sessions[session_id] = {
            "state": "await_start_confirmation",
            "created_at": time.time(),
            "updated_at": time.time(),
            "user_id": user_id,
            "profile": user_profile or {},
            "product": {},
            "order": {},
            "payment": {},
        }
        return session_id

    def _cleanup_stale_sessions(self) -> None:
        now = time.time()
        to_delete: List[str] = []
        for sid, session in self.sessions.items():
            if now - float(session.get("updated_at", now)) > self.SESSION_TIMEOUT_SECONDS:
                to_delete.append(sid)
        for sid in to_delete:
            del self.sessions[sid]

    def _prompt_for_state(self, session: Dict[str, Any]) -> str:
        prompts = {
            "await_start_confirmation": "Hi! Do you want to place an order from a product link? (yes/no)",
            "await_product_link": "Please paste the product link of the item you want to order.",
            "await_manual_name": "Please enter the product name.",
            "await_manual_price": "Please enter the product price (numbers only, for example 4990).",
            "await_manual_options": "Please enter available sizes only, comma-separated (example: S, L, XL).",
            "await_manual_store": "Please enter the store or website name.",
            "await_product_confirmation": "Is this the correct product? (yes/no)",
            "await_quantity": "How many items do you want to order?",
            "await_variant": "Which size do you want?",
            "await_color": "Which color do you want?",
            "await_summary_confirmation": "Please confirm that all details are correct. Should we proceed to payment? (yes/no)",
            "await_checkout_action": "Would you like to continue with Add to Cart or Buy Now?",
            "await_profile_confirmation": "Please confirm your profile details for Buy Now. Are these correct? (yes/no)",
            "await_edit_choice": "Which detail do you want to edit: quantity, variant, or color?",
            "await_payment_method": "Select payment method: Card / PayPal / Cash on Delivery",
            "await_payment_completion": "Please complete payment on the secure page and type DONE when finished, or CANCEL to stop.",
            "await_final_confirmation": "Type CONFIRM to place the order or CANCEL to stop.",
            "await_order_placed_confirmation": "Have you placed the order on the checkout page? (yes/no)",
            "await_another_url_decision": "Do you want to proceed with another product URL? (yes/no)",
        }
        return prompts.get(session.get("state", ""), "Please continue.")

    def _handle_start_confirmation(self, session_id: str, text: str) -> Dict[str, Any]:
        yes_no = self._parse_yes_no(text)
        if yes_no is None:
            return {
                "session_id": session_id,
                "state": "await_start_confirmation",
                "reply": "Please choose Yes or No.",
                "requires_input": True,
            }

        session = self.sessions[session_id]
        if not yes_no:
            session["state"] = "canceled"
            return {
                "session_id": session_id,
                "state": "canceled",
                "reply": "No problem. I am here when you are ready.",
                "completed": True,
            }

        session["state"] = "await_product_link"
        return {
            "session_id": session_id,
            "state": "await_product_link",
            "reply": "Please paste the product link of the item you want to order.",
            "requires_input": True,
        }

    def _handle_product_link(self, session_id: str, text: str) -> Dict[str, Any]:
        if not self._is_valid_url(text):
            return {
                "session_id": session_id,
                "state": "await_product_link",
                "reply": "Hmm, that does not look like a valid link. Can you paste it again?",
                "requires_input": True,
            }

        session = self.sessions[session_id]
        session.setdefault("product", {})["url"] = text

        product_info = self._extract_product_details(text)

        if not isinstance(product_info, dict):
            session["state"] = "await_product_link"
            return {
                "session_id": session_id,
                "state": "await_product_link",
                "reply": "Sorry, I couldn't retrieve the required data at the moment. Please try again later or share another URL so I can assist you.",
                "requires_input": True,
            }

        normalized = self._normalize_product(product_info, text)
        session["product"] = normalized

        session["state"] = "await_product_confirmation"
        return self._build_product_confirmation_response(session_id)

    def _handle_manual_product_fields(self, session_id: str, text: str) -> Dict[str, Any]:
        session = self.sessions[session_id]
        product = session.setdefault("product", {})
        state = session["state"]

        if state == "await_manual_name":
            if len(text.strip()) < 2:
                return {
                    "session_id": session_id,
                    "state": state,
                    "reply": "Please enter a valid product name.",
                    "requires_input": True,
                }
            product["name"] = text.strip()
            session["state"] = "await_manual_price"
            return {
                "session_id": session_id,
                "state": "await_manual_price",
                "reply": "Please enter the product price (numbers only, for example 4990).",
                "requires_input": True,
            }

        if state == "await_manual_price":
            price = self._parse_positive_float(text)
            if price is None:
                return {
                    "session_id": session_id,
                    "state": state,
                    "reply": "That price does not look right. Please enter numbers only.",
                    "requires_input": True,
                }
            product["price"] = price
            product.setdefault("currency", "LKR")
            session["state"] = "await_manual_options"
            return {
                "session_id": session_id,
                "state": "await_manual_options",
                "reply": "Please enter available sizes only, comma-separated (example: S, L, XL).",
                "requires_input": True,
            }

        if state == "await_manual_options":
            options = [opt.strip() for opt in text.split(",") if opt.strip()]
            if not options:
                return {
                    "session_id": session_id,
                    "state": state,
                    "reply": "Please enter at least one available size (example: S, L, XL).",
                    "requires_input": True,
                }
            product["available_options"] = options
            session["state"] = "await_manual_store"
            return {
                "session_id": session_id,
                "state": "await_manual_store",
                "reply": "Please enter the store or website name.",
                "requires_input": True,
            }

        if state == "await_manual_store":
            if len(text.strip()) < 2:
                return {
                    "session_id": session_id,
                    "state": state,
                    "reply": "Please enter a valid store name.",
                    "requires_input": True,
                }
            product["shop"] = text.strip()
            product.setdefault("availability", "Unknown")
            product.setdefault("shipping_availability", "Unknown")
            product.setdefault("estimated_delivery", self.order_agent._get_estimated_delivery(product.get("shop", "Unknown")))
            product.setdefault("currency", "LKR")
            session["state"] = "await_product_confirmation"
            return self._build_product_confirmation_response(session_id)

        return {
            "session_id": session_id,
            "state": state,
            "reply": "Please continue with the requested product detail.",
            "requires_input": True,
        }

    def _build_product_confirmation_response(self, session_id: str) -> Dict[str, Any]:
        session = self.sessions[session_id]
        product = session.get("product", {})
        options = product.get("available_options") or []
        colors = product.get("available_colors") or []
        variants = product.get("variants") or {}
        size_variants = variants.get("sizes") if isinstance(variants, dict) else []
        color_variants = variants.get("colors") if isinstance(variants, dict) else []
        all_sizes = self._dedupe_values([*(options if isinstance(options, list) else []), *(size_variants if isinstance(size_variants, list) else [])])
        all_colors = self._dedupe_values([*(colors if isinstance(colors, list) else []), *(color_variants if isinstance(color_variants, list) else [])])
        lines = [
            "Fetched product details:",
            f"Shop: {product.get('shop', 'Unknown')}",
            f"Product: {product.get('name', 'Unknown')}",
        ]

        source_price = float(product.get("price", 0.0) or 0.0)
        source_currency = str(product.get("currency", "LKR"))
        if source_price > 0:
            lkr_price = self._to_lkr(source_price, source_currency)
            lines.append(f"Price: LKR {lkr_price:.2f}")
        if all_sizes:
            lines.append(f"Available Sizes: {', '.join(all_sizes)}")
        if all_colors:
            lines.append(f"Available Colors: {', '.join(all_colors)}")
        if product.get("availability"):
            lines.append(f"Stock: {product.get('availability')}")
        if product.get("url"):
            lines.append(f"Product Link: {product.get('url')}")

        reply = "\n".join(lines) + "\n\nIs this the correct product? (yes/no)"
        return {
            "session_id": session_id,
            "state": "await_product_confirmation",
            "reply": reply,
            "product": product,
            "requires_input": True,
        }

    def _handle_product_confirmation(self, session_id: str, text: str) -> Dict[str, Any]:
        yes_no = self._parse_yes_no(text)
        if yes_no is None:
            return {
                "session_id": session_id,
                "state": "await_product_confirmation",
                "reply": "Please choose Yes or No.",
                "requires_input": True,
            }

        session = self.sessions[session_id]
        if not yes_no:
            session["state"] = "await_product_link"
            return {
                "session_id": session_id,
                "state": "await_product_link",
                "reply": "Okay, please paste another product link.",
                "requires_input": True,
            }

        session["state"] = "await_quantity"
        return {
            "session_id": session_id,
            "state": "await_quantity",
            "reply": "How many items do you want to order?",
            "requires_input": True,
        }

    def _handle_quantity(self, session_id: str, text: str) -> Dict[str, Any]:
        qty = self._parse_positive_int(text)
        if qty is None or qty > 20:
            return {
                "session_id": session_id,
                "state": "await_quantity",
                "reply": "That does not look right, please enter a valid quantity (1-20).",
                "requires_input": True,
            }

        session = self.sessions[session_id]
        session.setdefault("order", {})["quantity"] = qty

        product = session.get("product", {})
        variants = product.get("variants") if isinstance(product, dict) else {}
        variant_sizes = variants.get("sizes") if isinstance(variants, dict) else []
        options = self._dedupe_values([*(product.get("available_options") or []), *(variant_sizes or [])])
        if options:
            session["state"] = "await_variant"
            return {
                "session_id": session_id,
                "state": "await_variant",
                "reply": f"Please choose your size from available sizes: {', '.join(options)}",
                "requires_input": True,
            }

        session["order"]["variant"] = "N/A"
        return self._advance_after_variant(session_id)

    def _handle_variant(self, session_id: str, text: str) -> Dict[str, Any]:
        session = self.sessions[session_id]
        product = session.get("product", {})
        variants = product.get("variants") if isinstance(product, dict) else {}
        variant_sizes = variants.get("sizes") if isinstance(variants, dict) else []
        all_options = self._dedupe_values([*(product.get("available_options") or []), *(variant_sizes or [])])
        options = [opt.strip().lower() for opt in all_options]
        selected = text.strip()
        if options and selected.lower() not in options:
            matched = self._match_choice(all_options, selected)
            if matched is None:
                return {
                    "session_id": session_id,
                    "state": "await_variant",
                    "reply": "That size is not currently available. Please choose one listed available size.",
                    "requires_input": True,
                }
            selected = matched

        session.setdefault("order", {})["variant"] = selected
        return self._advance_after_variant(session_id)

    def _advance_after_variant(self, session_id: str) -> Dict[str, Any]:
        session = self.sessions[session_id]
        product = session.get("product", {})
        variants = product.get("variants") if isinstance(product, dict) else {}
        variant_colors = variants.get("colors") if isinstance(variants, dict) else []
        colors = self._dedupe_values([*(product.get("available_colors") or []), *(variant_colors or [])])
        if colors:
            session["state"] = "await_color"
            return {
                "session_id": session_id,
                "state": "await_color",
                "reply": f"Please choose your color from available colors: {', '.join(colors)}",
                "requires_input": True,
            }

        session.setdefault("order", {})["color"] = "N/A"
        session["state"] = "await_summary_confirmation"
        return self._build_order_summary_response(session_id)

    def _handle_color(self, session_id: str, text: str) -> Dict[str, Any]:
        session = self.sessions[session_id]
        product = session.get("product", {})
        variants = product.get("variants") if isinstance(product, dict) else {}
        variant_colors = variants.get("colors") if isinstance(variants, dict) else []
        all_colors = self._dedupe_values([*(product.get("available_colors") or []), *(variant_colors or [])])
        colors = [c.strip().lower() for c in all_colors]
        selected = text.strip()
        if colors and selected.lower() not in colors:
            matched = self._match_choice(all_colors, selected)
            if matched is None:
                return {
                    "session_id": session_id,
                    "state": "await_color",
                    "reply": "That color is not currently available. Please choose one listed available color.",
                    "requires_input": True,
                }
            selected = matched

        session.setdefault("order", {})["color"] = selected if selected else "N/A"
        session["state"] = "await_summary_confirmation"
        return self._build_order_summary_response(session_id)

    def _build_order_summary_response(self, session_id: str) -> Dict[str, Any]:
        session = self.sessions[session_id]
        product = session.get("product", {})
        order = session.get("order", {})
        profile = session.get("profile", {}) or {}

        # Personal details come from selected user profile, not chat prompts.
        order["shipping_address"] = str(profile.get("shipping_address") or "N/A")
        order["contact_number"] = str(profile.get("phone") or "N/A")
        order["email"] = str(profile.get("email") or "N/A")

        quantity = int(order.get("quantity", 1))
        source_currency = str(product.get("currency", "LKR"))
        source_unit_price = float(product.get("price", 0.0))
        unit_price = self._to_lkr(source_unit_price, source_currency)
        shipping_fee = self._estimate_shipping_fee_lkr(product)
        total_cost = unit_price * quantity + shipping_fee

        order["unit_price"] = unit_price
        order["shipping_fee"] = shipping_fee
        order["total_cost"] = total_cost

        price_line = f"Price LKR: {unit_price:.2f}"

        summary = (
            "Order summary:\n"
            f"Product: {product.get('name', 'Unknown')}\n"
            f"{price_line}\n"
            f"Quantity: {quantity}\n"
            f"Size: {order.get('variant', 'N/A')}\n"
            f"Color: {order.get('color', 'N/A')}\n"
            f"Estimated Shipping (LKR): {shipping_fee:.2f}\n"
            f"Total Estimated Cost (LKR): {total_cost:.2f}\n"
            f"Shipping Address: {order.get('shipping_address', 'N/A')}\n"
            f"Contact Number: {order.get('contact_number', 'N/A')}\n"
            f"Contact Email: {order.get('email', 'N/A')}\n\n"
            "Please confirm that all details are correct. Should we proceed to payment? (yes/no)"
        )

        return {
            "session_id": session_id,
            "state": "await_summary_confirmation",
            "reply": summary,
            "summary": {
                "currency": "LKR",
                "unit_price": unit_price,
                "quantity": quantity,
                "variant": order.get("variant", "N/A"),
                "color": order.get("color", "N/A"),
                "shipping_fee": shipping_fee,
                "total_cost": total_cost,
            },
            "requires_input": True,
        }

    def _handle_summary_confirmation(self, session_id: str, text: str) -> Dict[str, Any]:
        session = self.sessions[session_id]
        order = session.setdefault("order", {})

        # Allow direct chat edits such as: "change quantity to 2 size M color black".
        inline_updates, update_error = self._extract_inline_order_updates(session, text)
        if update_error:
            return {
                "session_id": session_id,
                "state": "await_summary_confirmation",
                "reply": update_error,
                "requires_input": True,
            }
        if inline_updates:
            order.update(inline_updates)
            refreshed = self._build_order_summary_response(session_id)
            refreshed["reply"] = (
                "Updated order details from your message.\n\n"
                + str(refreshed.get("reply", ""))
            )
            return refreshed

        normalized = text.strip().lower()
        if ("edit" in normalized or "change" in normalized or "modify" in normalized) and not self._parse_yes_no(text):
            session["state"] = "await_edit_choice"
            return {
                "session_id": session_id,
                "state": "await_edit_choice",
                "reply": "Sure. What do you want to edit: quantity, variant, or color?",
                "requires_input": True,
            }

        yes_no = self._parse_yes_no(text)
        if yes_no is None:
            return {
                "session_id": session_id,
                "state": "await_summary_confirmation",
                "reply": "Please choose Yes or No.",
                "requires_input": True,
            }

        if not yes_no:
            session["state"] = "await_edit_choice"
            return {
                "session_id": session_id,
                "state": "await_edit_choice",
                "reply": "Do you want to edit quantity, variant, or color?",
                "requires_input": True,
            }

        session["state"] = "await_profile_confirmation"
        return self._build_profile_confirmation_response(session_id)

    def _extract_inline_order_updates(self, session: Dict[str, Any], text: str) -> tuple[Dict[str, Any], Optional[str]]:
        updates: Dict[str, Any] = {}
        normalized_text = text.strip().lower()
        product = session.get("product", {}) if isinstance(session, dict) else {}

        qty_match = re.search(r"\b(?:qty|quantity)\s*(?:is|to|=)?\s*(\d{1,2})\b", normalized_text)
        if qty_match:
            qty = int(qty_match.group(1))
            if qty < 1 or qty > 20:
                return {}, "Quantity must be between 1 and 20."
            updates["quantity"] = qty

        size_match = re.search(r"\b(?:size|variant)\s*(?:is|to|=)?\s*([a-z0-9][a-z0-9\-_/+]*)\b", normalized_text)
        if size_match:
            size_value = size_match.group(1).strip()
            variants = product.get("variants") if isinstance(product, dict) else {}
            variant_sizes = variants.get("sizes") if isinstance(variants, dict) else []
            allowed_sizes = self._dedupe_values([*(product.get("available_options") or []), *(variant_sizes or [])])
            if allowed_sizes:
                matched_size = self._match_choice(allowed_sizes, size_value)
                if matched_size is None:
                    return {}, "That size is not available. Please choose one of the listed sizes."
                updates["variant"] = matched_size
            else:
                updates["variant"] = size_value

        color_match = re.search(r"\bcolor\s*(?:is|to|=)?\s*([a-z0-9][a-z0-9\-_/+]*)\b", normalized_text)
        if color_match:
            color_value = color_match.group(1).strip()
            variants = product.get("variants") if isinstance(product, dict) else {}
            variant_colors = variants.get("colors") if isinstance(variants, dict) else []
            allowed_colors = self._dedupe_values([*(product.get("available_colors") or []), *(variant_colors or [])])
            if allowed_colors:
                matched_color = self._match_choice(allowed_colors, color_value)
                if matched_color is None:
                    return {}, "That color is not available. Please choose one of the listed colors."
                updates["color"] = matched_color
            else:
                updates["color"] = color_value

        if not updates:
            compact = re.sub(r"\s+", " ", normalized_text)
            if compact.isdigit():
                qty = int(compact)
                if 1 <= qty <= 20:
                    updates["quantity"] = qty

        return updates, None

    def _handle_checkout_action(self, session_id: str, text: str) -> Dict[str, Any]:
        choice = text.strip().lower()
        session = self.sessions[session_id]
        product = session.get("product", {})
        review_link = session.get("payment", {}).get("review_link") or product.get("checkout_url") or product.get("buy_now_url") or product.get("url")

        if "review" in choice:
            return {
                "session_id": session_id,
                "state": "await_checkout_action",
                "reply": (
                    f"Review details page: {review_link}\n\n"
                    "After reviewing details, choose Buy Now or Add to Cart."
                ),
                "requires_input": True,
            }

        if "add" in choice and "cart" in choice:
            order = session.get("order", {})
            quantity = int(order.get("quantity", 1))
            variant = order.get("variant")
            cart_result = self.order_agent.add_product(
                str(product.get("url", "")),
                quantity=quantity,
                size=variant if isinstance(variant, str) and variant != "N/A" else None,
                color=order.get("color") if isinstance(order.get("color"), str) and order.get("color") != "N/A" else None,
                user_id=session.get("user_id"),
            )
            session.setdefault("payment", {})["checkout_action"] = "add_to_cart"
            session["state"] = "completed"
            ext_cart = product.get("add_to_cart_url") or review_link
            status = "added" if cart_result.get("success") else "could not add automatically"
            return {
                "session_id": session_id,
                "state": "completed",
                "reply": (
                    f"I {status} to your app cart with selected details.\n"
                    f"Review/Add-to-cart page link: {ext_cart}\n\n"
                    "If the external shop requires login, please complete it manually on that page."
                ),
                "completed": True,
                "requires_input": True,
            }

        if "buy" in choice or "now" in choice:
            session.setdefault("payment", {})["checkout_action"] = "buy_now"
            buy_now_link = product.get("buy_now_url") or product.get("checkout_url") or review_link
            session.setdefault("payment", {})["checkout_link"] = buy_now_link
            prefill_result = self.order_agent.automate_checkout_prefill(
                product=product,
                order=session.get("order", {}),
                profile=session.get("profile", {}),
            )
            filled_fields = prefill_result.get("filled_fields") or []
            filled_text = ", ".join(filled_fields) if filled_fields else "none detected"
            checkout_target = prefill_result.get("checkout_url") or buy_now_link
            shipping_fee = prefill_result.get("shipping_fee")
            if shipping_fee is not None:
                try:
                    shipping_fee_float = float(shipping_fee)
                    session.setdefault("product", {})["shipping_fee"] = shipping_fee_float
                    order = session.setdefault("order", {})
                    quantity = int(order.get("quantity", 1))
                    unit_price = float(order.get("unit_price", 0.0))
                    order["shipping_fee"] = shipping_fee_float
                    order["total_cost"] = unit_price * quantity + shipping_fee_float
                except Exception:
                    shipping_fee_float = None
            else:
                shipping_fee_float = None

            session.setdefault("payment", {})["checkout_link"] = checkout_target
            session["state"] = "await_payment_method"
            return {
                "session_id": session_id,
                "state": "await_payment_method",
                "checkout_url": checkout_target,
                "reply": (
                    f"Buy Now / Checkout page: {checkout_target}\n"
                    f"Prefill status: {prefill_result.get('message', 'No prefill status available.')}\n"
                    f"Prefilled fields: {filled_text}\n\n"
                    + (f"Checkout shipping fee detected: LKR {shipping_fee_float:.2f}\n\n" if shipping_fee_float is not None else "")
                    + "Select payment method in chat: Card, PayPal, or Cash on Delivery."
                ),
                "completed": False,
                "requires_input": True,
            }

        return {
            "session_id": session_id,
            "state": "await_checkout_action",
            "reply": "Please choose Review Details Page, Add to Cart, or Buy Now.",
            "requires_input": True,
        }

    def _build_profile_confirmation_response(self, session_id: str) -> Dict[str, Any]:
        session = self.sessions[session_id]
        profile = session.get("profile", {}) or {}
        product = session.get("product", {}) or {}
        reply = (
            "Profile details check:\n"
            f"Name: {profile.get('name', 'N/A')}\n"
            f"Email: {profile.get('email', 'N/A')}\n"
            f"Phone: {profile.get('phone', 'N/A')}\n"
            f"Shipping Address: {profile.get('shipping_address', 'N/A')}\n"
            f"Shop Page: {product.get('url', 'N/A')}\n\n"
            "Are these profile details correct?"
        )
        return {
            "session_id": session_id,
            "state": "await_profile_confirmation",
            "reply": reply,
            "profile": {
                "user_id": profile.get("user_id"),
                "name": profile.get("name"),
                "email": profile.get("email"),
                "phone": profile.get("phone"),
                "shipping_address": profile.get("shipping_address"),
            },
            "requires_input": True,
        }

    def _handle_profile_confirmation(self, session_id: str, text: str) -> Dict[str, Any]:
        session = self.sessions[session_id]
        choice = text.strip().lower()
        if choice in {"edit personal details", "edit", "no", "n", "save profile", "save"}:
            session["state"] = "await_profile_confirmation"
            return {
                "session_id": session_id,
                "state": "await_profile_confirmation",
                "reply": "Edit details in the user profile card and click Save.",
                "profile": {
                    "user_id": session.get("profile", {}).get("user_id"),
                    "name": session.get("profile", {}).get("name"),
                    "email": session.get("profile", {}).get("email"),
                    "phone": session.get("profile", {}).get("phone"),
                    "shipping_address": session.get("profile", {}).get("shipping_address"),
                },
                "requires_input": True,
            }

        yes_no = self._parse_yes_no(text)
        if yes_no is None and choice not in {"confirm details", "confirm", "yes", "y"}:
            return {
                "session_id": session_id,
                "state": "await_profile_confirmation",
                "reply": "Please choose Confirm Details or Edit Personal Details.",
                "requires_input": True,
            }

        profile = session.setdefault("profile", {})
        order = session.setdefault("order", {})
        order["shipping_address"] = str(profile.get("shipping_address") or "N/A")
        order["contact_number"] = str(profile.get("phone") or "N/A")
        order["email"] = str(profile.get("email") or "N/A")

        product = session.get("product", {}) or {}
        review_link = product.get("checkout_url") or product.get("buy_now_url") or product.get("url")
        session.setdefault("payment", {})["review_link"] = review_link
        session["state"] = "await_checkout_action"
        return {
            "session_id": session_id,
            "state": "await_checkout_action",
            "reply": (
                "Profile confirmed. I can now attempt a best-effort checkout prefill on the shop page using Playwright (no submit, no payment).\n"
                f"Review details page: {review_link}\n\n"
                "Choose what to do next: Review Details Page, Buy Now, or Add to Cart."
            ),
            "profile": {
                "user_id": profile.get("user_id"),
                "name": profile.get("name"),
                "email": profile.get("email"),
                "phone": profile.get("phone"),
                "shipping_address": profile.get("shipping_address"),
            },
            "requires_input": True,
        }

    def _handle_edit_choice(self, session_id: str, text: str) -> Dict[str, Any]:
        choice = text.strip().lower()
        session = self.sessions[session_id]

        if "quantity" in choice:
            session["state"] = "await_quantity"
            return {
                "session_id": session_id,
                "state": "await_quantity",
                "reply": "What quantity would you like to order?",
                "requires_input": True,
            }

        if "variant" in choice or "size" in choice:
            session["state"] = "await_variant"
            return {
                "session_id": session_id,
                "state": "await_variant",
                "reply": "Which size do you want?",
                "requires_input": True,
            }

        if "color" in choice:
            session["state"] = "await_color"
            return {
                "session_id": session_id,
                "state": "await_color",
                "reply": "Which color do you want?",
                "requires_input": True,
            }

        return {
            "session_id": session_id,
            "state": "await_edit_choice",
            "reply": "Please choose one detail to edit: quantity, variant, or color.",
            "requires_input": True,
        }

    def _handle_payment_method(self, session_id: str, text: str) -> Dict[str, Any]:
        method_key = text.strip().lower()
        normalized: Optional[str] = None
        if "card" in method_key or "credit" in method_key or "debit" in method_key:
            normalized = "Card"
        elif "paypal" in method_key:
            normalized = "PayPal"
        elif "cash" in method_key or "cod" in method_key:
            normalized = "Cash on Delivery"

        if normalized is None:
            return {
                "session_id": session_id,
                "state": "await_payment_method",
                "reply": "Please choose one of the available payment methods: Card, PayPal, or Cash on Delivery.",
                "requires_input": True,
            }

        session = self.sessions[session_id]
        payment = session.setdefault("payment", {})
        payment["method"] = normalized

        if normalized in {"Card", "PayPal"}:
            checkout_link = payment.get("checkout_link") or self._build_secure_checkout_link(session.get("product", {}), normalized)
            payment["checkout_link"] = checkout_link
            session["state"] = "await_order_placed_confirmation"
            return {
                "session_id": session_id,
                "state": "await_order_placed_confirmation",
                "checkout_url": checkout_link,
                "reply": (
                    f"For transparency: I cannot auto-charge your card or access private shop sessions. "
                    f"Please complete {normalized} payment yourself on this secure page: {checkout_link}\n"
                    "Add card details and review the filled fields there.\n"
                    "After payment, come back and tell me: Yes if placed order, No if not."
                ),
                "requires_input": True,
            }

        # COD path: no online payment page required.
        session["state"] = "await_order_placed_confirmation"
        return {
            "session_id": session_id,
            "state": "await_order_placed_confirmation",
            "reply": "Cash on Delivery selected. Place the order on the shop page and then tell me: Yes if placed order, No if not.",
            "requires_input": True,
        }

    def _handle_payment_completion(self, session_id: str, text: str) -> Dict[str, Any]:
        if text.strip().lower() not in {"done", "paid", "completed", "yes"}:
            return {
                "session_id": session_id,
                "state": "await_payment_completion",
                "reply": "Please type DONE after you complete payment on the secure page, or CANCEL to stop.",
                "requires_input": True,
            }

        session = self.sessions[session_id]
        session["state"] = "await_final_confirmation"
        return self._build_final_confirmation_response(session_id)

    def _build_final_confirmation_response(self, session_id: str) -> Dict[str, Any]:
        session = self.sessions[session_id]
        product = session.get("product", {})
        order = session.get("order", {})
        payment = session.get("payment", {})

        currency = "LKR"
        reply = (
            "Final Order Confirmation:\n\n"
            f"Product: {product.get('name', 'Unknown')}\n"
            f"Quantity: {order.get('quantity', 1)}\n"
            f"Total: {currency} {float(order.get('total_cost', 0.0)):.2f}\n"
            f"Shipping Address: {order.get('shipping_address', 'N/A')}\n"
            f"Payment Method: {payment.get('method', 'N/A')}\n\n"
            "Type CONFIRM to place the order or CANCEL to stop."
        )
        return {
            "session_id": session_id,
            "state": "await_final_confirmation",
            "reply": reply,
            "requires_input": True,
        }

    def _handle_final_confirmation(self, session_id: str, text: str) -> Dict[str, Any]:
        normalized = text.strip().upper()
        session = self.sessions[session_id]

        if normalized == "CANCEL":
            session["state"] = "canceled"
            return {
                "session_id": session_id,
                "state": "canceled",
                "reply": "Order canceled. Let me know if you'd like to try again.",
                "completed": True,
            }

        if normalized != "CONFIRM":
            return {
                "session_id": session_id,
                "state": "await_final_confirmation",
                "reply": "Please type CONFIRM to place the order or CANCEL to stop.",
                "requires_input": True,
            }

        session["state"] = "completed"
        return {
            "session_id": session_id,
            "state": "completed",
            "reply": "Your order request has been submitted successfully. You will receive confirmation shortly.",
            "completed": True,
        }

    def _handle_order_placed_confirmation(self, session_id: str, text: str) -> Dict[str, Any]:
        session = self.sessions[session_id]
        yes_no = self._parse_yes_no(text)
        if yes_no is None:
            return {
                "session_id": session_id,
                "state": "await_order_placed_confirmation",
                "reply": "Please answer Yes or No. Have you placed the order on the checkout page?",
                "requires_input": True,
            }

        if yes_no:
            self._record_order_in_kg(session)
            session["state"] = "await_another_url_decision"
            return {
                "session_id": session_id,
                "state": "await_another_url_decision",
                "reply": "Great. I have recorded this order. Do you want to proceed with another product URL? (yes/no)",
                "requires_input": True,
            }

        session["state"] = "await_another_url_decision"
        return {
            "session_id": session_id,
            "state": "await_another_url_decision",
            "reply": "No problem. Do you want to proceed with another product URL? (yes/no)",
            "requires_input": True,
        }

    def _handle_another_url_decision(self, session_id: str, text: str) -> Dict[str, Any]:
        session = self.sessions[session_id]
        yes_no = self._parse_yes_no(text)
        if yes_no is None:
            return {
                "session_id": session_id,
                "state": "await_another_url_decision",
                "reply": "Please answer Yes or No. Do you want to proceed with another product URL?",
                "requires_input": True,
            }

        if yes_no:
            # Keep profile and user context, reset product/order/payment only.
            session["product"] = {}
            session["order"] = {}
            session["payment"] = {}
            session["state"] = "await_product_link"
            return {
                "session_id": session_id,
                "state": "await_product_link",
                "reply": "Please paste the next product link. I will scrape it and continue the same flow.",
                "requires_input": True,
            }

        session["state"] = "completed"
        return {
            "session_id": session_id,
            "state": "completed",
            "reply": "Thanks. Have a great day. If you need another order later, just start a new chat.",
            "completed": True,
            "requires_input": True,
        }

    def _normalize_product(self, product: Dict[str, Any], url: str) -> Dict[str, Any]:
        name = str(product.get("name") or "").strip()
        price = float(product.get("price") or 0.0)
        currency = str(product.get("currency") or "LKR").strip().upper()
        shop = str(product.get("shop") or "").strip()
        variants = product.get("variants") if isinstance(product.get("variants"), dict) else {}
        variant_sizes = variants.get("sizes") if isinstance(variants, dict) else []
        variant_colors = variants.get("colors") if isinstance(variants, dict) else []

        options = [
            *(product.get("available_sizes") or []),
            *(product.get("available_options") or []),
            *(variant_sizes or []),
        ]
        if not isinstance(options, list):
            options = []

        colors = [
            *(product.get("available_colors") or []),
            *(product.get("colors") or []),
            *(variant_colors or []),
        ]
        if not isinstance(colors, list):
            colors = []

        stock_count = product.get("stock_count")
        try:
            stock_count = int(stock_count) if stock_count is not None else None
        except Exception:
            stock_count = None

        shipping_availability = str(
            product.get("shipping_availability") or product.get("shipping") or "Check at checkout"
        ).strip()
        shipping_fee = product.get("shipping_fee")
        try:
            shipping_fee = float(shipping_fee) if shipping_fee is not None else None
            if shipping_fee is not None and shipping_fee < 0:
                shipping_fee = None
        except Exception:
            shipping_fee = None

        normalized_options = self._dedupe_values([str(opt).strip() for opt in options if str(opt).strip()])
        normalized_colors = self._dedupe_values([str(c).strip() for c in colors if str(c).strip()])

        looks_like_size = getattr(self.order_agent, "_looks_like_size", None)
        if callable(looks_like_size):
            normalized_options = [opt for opt in normalized_options if looks_like_size(opt)]

        looks_like_color = getattr(self.order_agent, "_looks_like_color", None)
        if callable(looks_like_color):
            normalized_colors = [c for c in normalized_colors if looks_like_color(c)]

        return {
            "url": url,
            "name": name if name else "Unknown Product",
            "title": str(product.get("title") or name or "").strip() or "Unknown Product",
            "price": price,
            "currency": currency or "LKR",
            "shop": shop if shop else self._domain_from_url(url),
            "seller": str(product.get("seller") or shop or self._domain_from_url(url)).strip(),
            "image": product.get("image"),
            "available_options": normalized_options,
            "available_colors": normalized_colors,
            "variants": {
                "sizes": normalized_options,
                "colors": normalized_colors,
            },
            "availability": str(product.get("availability") or "Unknown"),
            "shipping_availability": shipping_availability,
            "shipping_fee": shipping_fee,
            "stock_count": stock_count,
            "estimated_delivery": str(product.get("estimated_delivery") or self.order_agent._get_estimated_delivery(shop or "Unknown")),
            "add_to_cart_url": product.get("add_to_cart_url"),
            "buy_now_url": product.get("buy_now_url"),
            "checkout_url": product.get("checkout_url"),
        }

    def _extract_product_details(self, url: str) -> Optional[Dict[str, Any]]:
        """Try resilient extraction for real-world links.

        Order:
        1) Match existing dataset URL (best reliability).
        2) Scrape live page.
        """
        # 1) Try product lookup from local dataset by exact URL match.
        loader = getattr(self.order_agent, "loader", None)
        products = getattr(loader, "products", None) if loader is not None else None
        if products is not None and not getattr(products, "empty", True):
            try:
                rows = products[products["product_url"].astype(str).str.strip() == str(url).strip()]
                if not rows.empty:
                    row = rows.iloc[0].to_dict()
                    return {
                        "name": row.get("name") or "Unknown Product",
                        "title": row.get("name") or "Unknown Product",
                        "price": float(row.get("price_LKR") or 0.0),
                        "currency": "LKR",
                        "shop": str(row.get("shop_id") or self._domain_from_url(url)),
                        "seller": str(row.get("shop_id") or self._domain_from_url(url)),
                        "image": row.get("image") if isinstance(row, dict) else None,
                        "available_sizes": self._parse_size_range(row.get("size_range")),
                        "available_colors": self._parse_color_values(row.get("color")),
                        "variants": {
                            "sizes": self._parse_size_range(row.get("size_range")),
                            "colors": self._parse_color_values(row.get("color")),
                        },
                        "availability": "In Stock",
                        "shipping_availability": "Shipping available",
                        "stock_count": None,
                        "estimated_delivery": self.order_agent._get_estimated_delivery(str(row.get("shop_id") or "Unknown")),
                    }
            except Exception:
                pass

        # 2) Try live scraping.
        try:
            scraped = self.order_agent._scrape_product(url)
            if isinstance(scraped, dict):
                return scraped
        except Exception:
            pass

        return None

    def _get_missing_critical_fields(self, product: Dict[str, Any]) -> List[str]:
        missing: List[str] = []
        if not product.get("name") or str(product.get("name")).lower() == "unknown product":
            missing.append("name")
        return missing

    def decorate_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Attach UI hint metadata so frontend can render selection buttons."""
        if not isinstance(response, dict):
            return response

        state = str(response.get("state") or "")
        session_id = response.get("session_id")
        session = self.sessions.get(str(session_id), {}) if session_id else {}
        product = session.get("product", {}) if isinstance(session, dict) else {}

        select_by_state: Dict[str, List[str]] = {
            "await_start_confirmation": ["Yes", "No"],
            "await_product_confirmation": ["Yes", "No"],
            "await_quantity": ["1", "2", "3", "4", "5"],
            "await_summary_confirmation": ["Yes", "No"],
            "await_checkout_action": ["Review Details Page", "Add to Cart", "Buy Now"],
            "await_profile_confirmation": ["Confirm Details", "Edit Personal Details"],
            "await_edit_choice": ["quantity", "variant", "color"],
            "await_payment_method": ["Card", "PayPal", "Cash on Delivery"],
            "await_payment_completion": ["DONE", "CANCEL"],
            "await_final_confirmation": ["CONFIRM", "CANCEL"],
            "await_manual_store": list(self.COMMON_STORES),
            "await_manual_price": ["1500", "2500", "5000", "10000"],
        }

        if state == "await_variant":
            options = product.get("available_options") or []
            if options:
                response["input_type"] = "select"
                response["options"] = [str(opt) for opt in options]
            else:
                response["input_type"] = "text"
            return response

        if state == "await_color":
            colors = product.get("available_colors") or []
            if colors:
                response["input_type"] = "select"
                response["options"] = [str(color) for color in colors]
            else:
                response["input_type"] = "text"
            return response

        if state in select_by_state:
            response["input_type"] = "select"
            response["options"] = select_by_state[state]
            return response

        if state == "await_order_placed_confirmation":
            response["input_type"] = "select"
            response["options"] = ["Yes", "No"]
            return response

        if state == "await_another_url_decision":
            response["input_type"] = "select"
            response["options"] = ["Yes", "No"]
            return response

        response["input_type"] = "text"
        return response

    def _parse_size_range(self, raw_value: Any) -> List[str]:
        if raw_value is None:
            return []
        text = str(raw_value).strip()
        if not text:
            return []
        split_values = re.split(r"[,/|]", text)
        sizes = [v.strip() for v in split_values if v and v.strip() and v.strip().lower() not in {"n/a", "na"}]
        seen = set()
        deduped: List[str] = []
        for size in sizes:
            key = size.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(size)
        return deduped

    def _parse_color_values(self, raw_value: Any) -> List[str]:
        if raw_value is None:
            return []
        text = str(raw_value).strip()
        if not text:
            return []
        split_values = re.split(r"[,/|]", text)
        colors = [v.strip() for v in split_values if v and v.strip() and v.strip().lower() not in {"n/a", "na"}]
        seen = set()
        deduped: List[str] = []
        for color in colors:
            key = color.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(color)
        return deduped

    def _dedupe_values(self, values: List[str]) -> List[str]:
        seen = set()
        deduped: List[str] = []
        for value in values:
            key = value.strip().lower()
            if not key:
                continue
            if key in seen:
                continue
            seen.add(key)
            deduped.append(value.strip())
        return deduped

    def _canonical_choice(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())

    def _match_choice(self, available: List[str], selected: str) -> Optional[str]:
        selected_raw = str(selected or "").strip()
        if not selected_raw:
            return None
        selected_key = self._canonical_choice(selected_raw)
        for option in available:
            option_text = str(option or "").strip()
            if not option_text:
                continue
            option_key = self._canonical_choice(option_text)
            if not option_key:
                continue
            if selected_key == option_key:
                return option_text
            if selected_key and selected_key in option_key:
                return option_text
        return None

    def _state_for_missing_field(self, field_name: str) -> str:
        mapping = {
            "name": "await_manual_name",
            "price": "await_manual_price",
            "options": "await_manual_options",
            "store": "await_manual_store",
        }
        return mapping.get(field_name, "await_manual_name")

    def _estimate_shipping_fee(self, product: Dict[str, Any]) -> float:
        explicit_shipping_fee = product.get("shipping_fee")
        if explicit_shipping_fee is not None:
            try:
                fee = float(explicit_shipping_fee)
                if fee >= 0:
                    return fee
            except Exception:
                pass

        shipping_text = str(product.get("shipping_availability") or "").lower()
        if "free" in shipping_text:
            return 0.0
        if "unavailable" in shipping_text or "not available" in shipping_text:
            return 1000.0

        currency = str(product.get("currency") or "LKR").upper()
        base_by_currency = {
            "LKR": 450.0,
            "USD": 4.5,
            "EUR": 4.0,
            "GBP": 3.8,
        }
        return float(base_by_currency.get(currency, 450.0))

    def _build_secure_checkout_link(self, product: Dict[str, Any], method: str) -> str:
        preferred = product.get("checkout_url") or product.get("buy_now_url")
        if isinstance(preferred, str) and preferred.startswith("http"):
            return preferred
        parsed = urlparse(str(product.get("url") or ""))
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}/checkout?method={method.lower()}"
        return f"https://checkout.stylesensesl.example/pay?method={method.lower()}"

    def _to_lkr(self, amount: float, currency: str) -> float:
        rates = {
            "LKR": 1.0,
            "USD": 330.0,
            "EUR": 360.0,
            "GBP": 420.0,
        }
        return float(amount) * float(rates.get(str(currency).upper(), 1.0))

    def _estimate_shipping_fee_lkr(self, product: Dict[str, Any]) -> float:
        source_shipping = self._estimate_shipping_fee(product)
        return self._to_lkr(source_shipping, str(product.get("currency", "LKR")))

    def _is_valid_url(self, text: str) -> bool:
        try:
            parsed = urlparse(text.strip())
            return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
        except Exception:
            return False

    def _is_valid_email(self, text: str) -> bool:
        return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", text.strip()))

    def _parse_yes_no(self, text: str) -> Optional[bool]:
        val = text.strip().lower()
        if val in {"yes", "y"}:
            return True
        if val in {"no", "n"}:
            return False
        return None

    def _parse_positive_int(self, text: str) -> Optional[int]:
        try:
            value = int(text.strip())
            return value if value > 0 else None
        except Exception:
            return None

    def _parse_positive_float(self, text: str) -> Optional[float]:
        cleaned = re.sub(r"[^0-9.]", "", text)
        try:
            value = float(cleaned)
            return value if value > 0 else None
        except Exception:
            return None

    def _domain_from_url(self, url: str) -> str:
        try:
            return urlparse(url).netloc or "Unknown"
        except Exception:
            return "Unknown"

    def _guess_name_from_url(self, url: str) -> str:
        try:
            path = urlparse(url).path.strip("/")
            slug = path.split("/")[-1] if path else ""
            slug = unquote(slug)
            slug = re.sub(r"[-_]+", " ", slug)
            slug = re.sub(r"[^A-Za-z0-9\s]", " ", slug)
            slug = re.sub(r"\s+", " ", slug).strip()
            if len(slug) >= 3:
                return slug.title()
        except Exception:
            pass
        return "Unknown Product"

    def _record_order_in_kg(self, session: Dict[str, Any]) -> None:
        """Best-effort KG write for successful checkout confirmations."""
        try:
            user_id = str(session.get("user_id") or "anonymous")
            product = session.get("product", {}) or {}
            order = session.get("order", {}) or {}
            product_url = str(product.get("url") or "")
            product_name = str(product.get("name") or "Unknown Product")
            quantity = int(order.get("quantity") or 1)
            total_cost = float(order.get("total_cost") or 0.0)

            if not product_url:
                return

            self.order_agent.kg_client.execute_write(
                """
                MERGE (u:User {user_id: toString($user_id)})
                MERGE (p:Product {product_url: $product_url})
                SET p.name = coalesce(p.name, $product_name)
                MERGE (u)-[r:ORDERED]->(p)
                SET r.count = coalesce(r.count, 0) + 1,
                    r.last_quantity = $quantity,
                    r.last_total = $total_cost,
                    r.ts = datetime()
                """,
                {
                    "user_id": user_id,
                    "product_url": product_url,
                    "product_name": product_name,
                    "quantity": quantity,
                    "total_cost": total_cost,
                },
            )
        except Exception:
            # KG update should never break user checkout flow.
            return
