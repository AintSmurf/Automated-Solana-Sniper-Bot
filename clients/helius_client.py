from services.bot_context import BotContext
from spl.token.constants import TOKEN_PROGRAM_ID as SPL_TOKEN_PROGRAM_ID
from helpers.framework_utils import lamports_to_decimal,get_payload
import time



class HeliusClient:
    
    def __init__(self, ctx:BotContext):
        self.ctx = ctx
        self.logger = ctx.get("logger")
        self.special_logger = ctx.get("special_logger")
        self.helius_requests = ctx.get("helius_requests")
        self.helius_enhanced = ctx.get("helius_enhanced")
        self.api_key = ctx.api_keys.get("helius")
        self._id = 1
        self.prepare_json_files()
    
    def prepare_json_files(self):
        self.transaction_simulation_paylod = get_payload("Transaction_simulation")
        self.send_transaction_payload = get_payload("Send_transaction")
        self.asset_payload = get_payload("Asset_payload")
        self.largest_accounts_payload = get_payload("Largets_accounts")
        self.token_account_by_owner = get_payload("Token_account_by_owner")
        self.get_transaction_payload = get_payload("Get_transaction")
        self.signature_for_adress = get_payload("Signature_for_adress")
        self.account_balance = get_payload("Account_balance")
        self.get_signature_status = get_payload("Get_signature_statuses")
        self.helius_enhanced_payload = get_payload("Enhanced_transactions")
    
    def get_balance(self,pubkey: str)->int:
        self.account_balance["id"] = self._next_id()
        self.account_balance["params"][0] = pubkey
        try:
            self.ctx.get("helius_rl").wait()
            response_json = self.helius_requests.post(
                endpoint=self.api_key,
                payload=self.account_balance,
            )
            result = self._assert_response_ok(response_json, f"get_balance {pubkey}")
            if not result:
                return None
            value  = result.get("value", {})
            if not value:
                     return 0
            return lamports_to_decimal(value,9)
        except Exception as e:
                    self.logger.error(f"❌ Failed to retrive balance: {e}", exc_info=True)
                    return 0
    
    def get_token_accounts_by_owner(self, pubkey: str)->dict:
        self.token_account_by_owner["id"] = self._next_id()
        self.token_account_by_owner["params"][0] = pubkey
        self.token_account_by_owner["params"][1]["programId"] = str(SPL_TOKEN_PROGRAM_ID)

        try:
            self.ctx.get("helius_rl").wait()
            response_json = self.helius_requests.post(
                endpoint=self.api_key,
                payload=self.token_account_by_owner,
            )

            self.special_logger.debug(f"🔍 Raw Helius token accounts by owner Response: {response_json}")

            result = self._assert_response_ok(response_json, f"get_token_accounts_by_owner {pubkey}")
            if not result:
                return None

            accounts = result.get("value", {}).get("accounts", [])
            reserves = []

            for acc in accounts:
                parsed_info = acc["account"]["data"]["parsed"]["info"]
                ta = parsed_info["tokenAmount"]
                reserves.append({
                    "mint": parsed_info["mint"],
                    "amount": int(ta["amount"]),
                    "decimals": int(ta["decimals"]),
                })
            return reserves
        except Exception as e:
                    self.logger.error(f"❌ Failed to fetch account reserves: {e}", exc_info=True)
                    return []
    
    def get_token_meta_data(self, token_address: str)->dict:
        self.logger.info(f"🔍 Fetching metadata for {token_address} using Helius...")
        self.ctx.get("helius_rl").wait()
        self.asset_payload["id"] = self._next_id()
        self.asset_payload["params"]["id"] = token_address     
        response_json = self.helius_requests.post(
                endpoint=self.api_key,
                payload=self.asset_payload,
            )
        try:
            result = self._assert_response_ok(response_json, f"get_token_meta_data {token_address}")
            content = result.get("content", {})

            token_name = content.get("metadata", {}).get("name")
            token_image = content.get("links", {}).get("image")
            token_address = result.get("id")

            return {
                "name": token_name,
                "image": token_image,
                "token_address": token_address,
            }
        except Exception as e:
            self.logger.error(f"❌ Error fetching token data: {e}")
            return {}

    def get_token_decimals(self, token_address: str)->int:
        self.logger.info(f"🔍 retriving decimals for {token_address} using Helius...")
        self.ctx.get("helius_rl").wait()
        self.asset_payload["id"] = self._next_id()
        self.asset_payload["params"]["id"] = token_address     
        response_json = self.helius_requests.post(
                endpoint=self.api_key,
                payload=self.asset_payload,
            )
        try:
            result = self._assert_response_ok(response_json, f"get_token_decimals {token_address}")
            token_decimals = result.get("token_info", {}).get("decimals", {})
            return token_decimals
        except Exception as e:
            self.logger.error(f"❌ Error fetching token data: {e}")
            return 0

    def send_transaction(self,txn_64:str)->str:
        try:
            self.logger.info(f"sending transaction for signature: {txn_64}")
            self.ctx.get("helius_rl").wait()
            self.send_transaction_payload["id"] = self._next_id()
            self.send_transaction_payload["params"][0] = txn_64
            response_json = self.helius_requests.post(
                self.api_key, payload=self.send_transaction_payload
            )
            self.logger.debug(f"transaction response: {response_json}")          
            transaction_signature =  self._assert_response_ok(response_json, f"send_transaction {txn_64}")
            return transaction_signature
        except Exception as e:
             self.logger.error(f"failed to send send_transaction {e}") 
             return None
    
    def simulate_transaction(self, txn_64:str)->str:
        """Simulate a transaction using Helius RPC"""
        try:
            self.ctx.get("helius_rl").wait()
            self.transaction_simulation_paylod["params"][0] = txn_64
            self.send_transaction_payload["id"] = self._next_id()
            response = self.helius_requests.post(
                endpoint=self.api_key,
                payload=self.transaction_simulation_paylod,
            )
            self.logger.debug(f"Transaction Simulation Response: {response}")

            self.logger.info("✅ Transaction simulation successful!")
            return True

        except Exception as e:
            self.logger.error(f"❌ Error simulating transaction: {e}")
            return False
    
    def verify_signature(self, signature: str) -> str | None:
        max_retries = 10   
        delay = 2          

        for attempt in range(1, max_retries + 1):
            try:
                self.ctx.get("helius_rl").wait()
                self.get_signature_status["params"][0] = [signature]
                self.get_signature_status["id"] = self._next_id()

                response = self.helius_requests.post(
                    endpoint=self.api_key,
                    payload=self.get_signature_status,
                )

                result = self._assert_response_ok(response, f"verify_signature {signature}")
                if not result:
                    time.sleep(delay)
                    continue

                status_data = result.get("value", [None])[0]
                if not status_data:
                    self.logger.warning(f"⚠️ Empty status for signature {signature} (attempt {attempt})")
                    time.sleep(delay)
                    continue

                status = status_data.get("confirmationStatus")
                if status in ("confirmed", "finalized"):
                    self.logger.info(f"✅ Signature {signature} {status}")
                    return status

                # Still pending or processed
                self.logger.debug(f"⏳ Signature {signature} still {status} (attempt {attempt})")
                time.sleep(delay)

            except Exception as e:
                self.logger.error(f"❌ Error verifying signature {signature} (attempt {attempt}): {e}", exc_info=True)
                time.sleep(delay)

        self.logger.error(f"❌ Failed to verify signature {signature} after {max_retries} attempts")
        return None

    def get_token_supply(self, token_address: str)->int:
        self.logger.info(f"🔍 retriving token supply for {token_address} using Helius...")
        self.ctx.get("helius_rl").wait()
        self.asset_payload["id"] = self._next_id()
        self.asset_payload["params"]["id"] = token_address     
        response_json = self.helius_requests.post(
                endpoint=self.api_key,
                payload=self.asset_payload,
            )
        try:
            result = self._assert_response_ok(response_json, f"get_token_supply {token_address}")
            token_supply = result.get("token_info", {}).get("supply", {})
            return lamports_to_decimal(token_supply,self.get_token_decimals(token_address))
        except Exception as e:
            self.logger.error(f"❌ Error fetching token data: {e}")
            return 0
    
    def get_recent_transactions_signatures_for_token(self, token_mint: str,until:str=None,before:str=None) -> list[str]:
        try:     
            self.ctx.get("helius_rl").wait()         
            self.signature_for_adress["id"] = self._next_id()
            self.signature_for_adress["params"][0] = token_mint
            if before:
                self.signature_for_adress["params"][1]["before"] = before  
            if until:
                self.signature_for_adress["params"][1]["until"] = until
            response = self.helius_requests.post(
                endpoint=self.api_key,
                payload=self.signature_for_adress
            )

            txs = self._assert_response_ok(response, f"get_recent_transactions_signatures_for_token {token_mint,until,before}")
            self.logger.debug(f"pulled transactions:{txs}")
            return txs
        except Exception as e:
            self.logger.error(f"❌ Failed to fetch recent TXs for token {token_mint}: {e}")
            return []  
    
    def get_token_age(self, mint_address: str) -> int | None:
        try:
            self.ctx.get("helius_rl").wait() 
            self.signature_for_adress["id"] = self._next_id()
            self.signature_for_adress["params"][0] = mint_address
            response = self.helius_requests.post(
                endpoint=self.api_key,
                payload=self.signature_for_adress
            )

            result = self._assert_response_ok(response, f"get_token_age {mint_address}")
            if not result: 
                return 0
            first_tx = result[0]
            if "blockTime" in first_tx and first_tx["blockTime"]:
                return int(time.time()) - int(first_tx["blockTime"])
        except Exception as e:
            self.logger.error(f"❌ Error fetching token age: {e}")
        return 0
    
    def get_mint_account_info(self, token_address: str)->dict:
        self.logger.info(f"🔍 retriving token info for {token_address} using Helius...")
        self.ctx.get("helius_rl").wait()
        self.asset_payload["id"] = self._next_id()
        self.asset_payload["params"]["id"] = token_address     
        response_json = self.helius_requests.post(
                endpoint=self.api_key,
                payload=self.asset_payload,
            )
        try:
            result =  self._assert_response_ok(response_json,f"get_mint_account_info {token_address}")
            frozen = result.get("ownership", {}).get("frozen",False )
            authorities = result.get("authorities", {})
            mutable = result.get("mutable", False)
            return {"authorities":authorities,"frozen":frozen,"mutable":mutable}
        except Exception as e:
            self.logger.error(f"❌ Error fetching token data: {e}")
            return {}
    
    def get_largest_accounts(self, token_mint: str)->bool:
        self.logger.info(f"🔍 Checking token holders for {token_mint} using Helius...")

        try:
            self.ctx.get("helius_rl").wait()
            self.largest_accounts_payload["id"] = self._next_id()
            self.largest_accounts_payload["params"][0] = token_mint
            response_json = self.helius_requests.post(
                endpoint=self.api_key,
                payload=self.largest_accounts_payload,
            )

            self.special_logger.debug(f"🔍 Raw Helius Largest Accounts Response: {response_json}")

            result = self._assert_response_ok(response_json,f"get_largest_accounts {token_mint}")
            holders = result["value"]
            total_supply = self.get_token_supply(token_mint)

            if total_supply == 0:
                self.logger.error("❌ Failed to fetch token supply. Skipping analysis.")
                return False

            # Sort holders by balance
            sorted_holders = sorted(holders, key=lambda x: float(x["uiAmount"]), reverse=True)
            
            #amount of holders
            if len(sorted_holders) < 20:
                return False

            top_holders = sorted_holders[:10]
            top_holder_percentages = [
                (float(holder["uiAmount"]) / total_supply) * 100 for holder in top_holders
            ]
            # 1. Top holder >30% → risky
            if top_holder_percentages[0] > 30:
                return False

            # 2. Top 5 holders >70% combined → risky
            if sum(top_holder_percentages[:5]) > 70:
                return False

            # 3. Uniform bot-like distribution (>5% each, nearly equal)
            if len(top_holder_percentages) > 1:
                min_pct = min(top_holder_percentages[1:])
                max_pct = max(top_holder_percentages[1:])
                if abs(max_pct - min_pct) < 0.01 and max_pct > 5:
                    return False

            # 4. If dev not top holder (<2%) but someone else has >6% → risky
            if top_holder_percentages[0] < 2 and max(top_holder_percentages[1:]) > 6:
                return False

            self.logger.info("✅ Token Holder Analysis Complete.")
            return True

        except Exception as e:
            self.logger.error(f"❌ Error fetching largest accounts from Helius: {e}")
            return False
    
    def get_transaction(self,signature:str):
        self.logger.debug(f"retriving transaction for signature: {signature} using Helius...")
        try:
            self.ctx.get("helius_rl").wait()
            self.get_transaction_payload["id"] = self._next_id()
            self.get_transaction_payload["params"][0] = signature
            response_json = self.helius_requests.post(
                endpoint=self.api_key,
                payload=self.get_transaction_payload,
            )

            self.special_logger.debug(f"🔍 Raw Helius Largest Accounts Response: {response_json}")
            result = self._assert_response_ok(response_json,f"get_transaction {signature}")
            return result
        except Exception as e:
            self.logger.error(f"failed to retrive transaction: {e}")   

    def _assert_response_ok(self, response: dict, description: str = "Helius call") -> dict | None:
        try:
            # 1️⃣ Type check
            if not isinstance(response, dict):
                self.logger.error(f"❌ {description}: Expected dict, got {type(response)}")

                fail_data = self.ctx.get("excel_utility").build_failed_rpc_calls(
                    description,
                    "INVALID_TYPE",
                    f"Expected dict, got {type(response)}"
                )
                self.ctx.get("excel_utility").save_failed_rpc(fail_data)
                return None
            if "error" in response:
                err = response["error"]
                code = err.get("code", "UNKNOWN")
                msg = err.get("message", "No message")
                data = err.get("data", "No data")

                self.logger.error(f"❌ {description}: RPC error {code}: {msg} | data={data}")

                fail_data = self.ctx.get("excel_utility").build_failed_rpc_calls(
                    description,
                    str(code),
                    f"{msg} | data={data}"
                )
                self.ctx.get("excel_utility").save_failed_rpc(fail_data)
                return None
            if "result" not in response:
                self.logger.error(f"❌ {description}: Missing 'result' key. Full response: {response}")

                fail_data = self.ctx.get("excel_utility").build_failed_rpc_calls(
                    description,
                    "NO_RESULT_KEY",
                    str(response)
                )
                self.ctx.get("excel_utility").save_failed_rpc(fail_data)
                return None
            return response["result"]

        except Exception as e:
            self.logger.error(f"❌ {description}: unexpected error: {e}", exc_info=True)

            fail_data = self.ctx.get("excel_utility").build_failed_rpc_calls(
                description,
                "EXCEPTION",
                str(e)
            )
            self.ctx.get("excel_utility").save_failed_rpc(fail_data)
            return None

    def get_enhanced_transactions_by_address(self,PDA:str):
        self.logger.info(f"retriving transactions for pair key: {PDA} using Helius...")
        try:
            self.ctx.get("helius_rl").wait()
            self._next_id()
            self.helius_enhanced_payload["api-key"] = self.api_key
            response_json = self.helius_enhanced.get(endpoint=f"v0/addresses/{PDA}/transactions" ,payload=self.helius_enhanced_payload)

            self.special_logger.debug(f"🔍 Raw Helius get_enhanced_transactions_by_address Response: {response_json}")
            return response_json
        except Exception as e:
            self.logger.error(f"failed to retrive transaction: {e}")   

    def get_holders_amount(self, token_mint: str)->int:
        self.logger.info(f"🔍 Checking token holders for {token_mint} using Helius...")

        try:
            self.ctx.get("helius_rl").wait()
            self.largest_accounts_payload["id"] = self._next_id()
            self.largest_accounts_payload["params"][0] = token_mint
            response_json = self.helius_requests.post(
                endpoint=self.api_key,
                payload=self.largest_accounts_payload,
            )

            self.special_logger.debug(f"🔍 Raw Helius Largest Accounts Response: {response_json}")

            result = self._assert_response_ok(response_json,f"get_largest_accounts {token_mint}")
            holders = result["value"]
            total_supply = self.get_token_supply(token_mint)

            if total_supply == 0:
                self.logger.error("❌ Failed to fetch token supply. Skipping analysis.")
                return 0
            sorted_holders = sorted(holders, key=lambda x: float(x["uiAmount"]), reverse=True)
        except Exception as e:
            self.logger.error(f"❌ Error fetching largest accounts from Helius: {e}")
            return 0
        return len(sorted_holders)
            
    def _next_id(self) ->int:
        self._id += 1
        return self._id


       