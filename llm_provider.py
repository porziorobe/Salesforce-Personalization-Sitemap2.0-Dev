import requests
from typing import Any, List, Optional, Mapping
from langchain_core.language_models.llms import LLM
from langchain_core.callbacks.manager import CallbackManagerForLLMRun


class ConnectAPILLM(LLM):
    authenticator: Any
    model: str = "sfdc_ai__DefaultBedrockAnthropicClaude46Sonnet"

    class Config:
        arbitrary_types_allowed = True

    @property
    def _llm_type(self) -> str:
        return "salesforce_connect_api"

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        if not self.authenticator.authenticated:
            self.authenticator.authenticate()

        url = f"https://api.salesforce.com/einstein/platform/v1/models/{self.model}/chat-generations"

        payload = {
            "messages": [{"role": "user", "content": prompt}],
        }

        headers = {
            "Authorization": f"Bearer {self.authenticator.access_token}",
            "Content-Type": "application/json",
            "x-sfdc-app-context": "EinsteinGPT",
            "x-client-feature-id": "ai-platform-models-connected-app",
        }

        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 401:
            self.authenticator.authenticate()
            headers["Authorization"] = f"Bearer {self.authenticator.access_token}"
            response = requests.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            raise Exception(
                f"Einstein API error: {response.status_code} - {response.text}"
            )

        data = response.json()
        return data["generationDetails"]["generations"][0]["content"]

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {"model": self.model}
