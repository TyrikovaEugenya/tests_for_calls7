import pytest
import allure
from tests.shared.base_user_flow_test import BaseUserFlowTest
import config
from utils import metrics


class TestGoodmovieUserFlow(BaseUserFlowTest):
    BASE_URL = "https://tests.goodmovie.net"
    SELECTORS = config.SELECTORS
    DOMAIN_NAME = "tests.goodmovie"


    @pytest.mark.parametrized
    @pytest.mark.domain_goodmovie
    @pytest.mark.browser_chromium
    @pytest.mark.parametrize("device", config.DEVICES)
    @pytest.mark.parametrize("throttling", config.THROTTLING_MODES)
    @pytest.mark.parametrize("geo", config.GEO_LOCATIONS)
    @pytest.mark.parametrize("browser_type", ["chromium"], scope="session")
    @pytest.mark.parametrize("pay_method", config.PAY_METHODS, scope="function")
    @allure.story("User Flow: Главная → Фильм → Плеер → Попап → Оплата")
    @allure.title("Полный user flow с Lighthouse (chromium)")
    def test_user_flow_chromium(self, page, get_film_url, device, throttling, geo, browser_type, pay_method, request):
        def main_page_step(page, request, report):
            dns_metrics = metrics.collect_network_metrics(page)
            self._goto_main_page(page, request, report)
            lh_data = self._collect_lighthouse_metrics(self.BASE_URL, request, report)
            report["steps"]["main_page"] = {
                **lh_data,
                "dnsResolveTime": dns_metrics["dnsResolveTime"],
                "connectTime": dns_metrics["connectTime"]
            }
            if lh_data["is_problematic_page"]:
                report["is_problematic_flow"] = True

        def film_page_step(page, request, report):
            dns_metrics = metrics.collect_network_metrics(page)
            lh_data = self._collect_lighthouse_metrics(get_film_url, request, report)
            report["steps"]["film_page"].update({
                **lh_data,
                "dnsResolveTime": dns_metrics["dnsResolveTime"],
                "connectTime": dns_metrics["connectTime"]
            })
            if lh_data["is_problematic_page"]:
                report["is_problematic_flow"] = True

        self.run_user_flow(
            page, get_film_url, device, throttling, geo, browser_type, pay_method, request,
            extra_steps={
                "main_page": main_page_step,
                "film_page_before_video": film_page_step
            }
        )


    @pytest.mark.parametrized
    @pytest.mark.domain_goodmovie
    @pytest.mark.browser_firefox
    @pytest.mark.browser_webkit
    @pytest.mark.parametrize("device", ["Desktop"])
    @pytest.mark.parametrize("throttling", ["No_throttling"])
    @pytest.mark.parametrize("geo", config.GEO_LOCATIONS)
    @pytest.mark.parametrize("browser_type", ["firefox", "webkit"], scope="session")
    @pytest.mark.parametrize("pay_method", config.PAY_METHODS, scope="function")
    @allure.story("User Flow: Главная → Фильм → Плеер → Попап → Оплата")
    @allure.title("User flow без Lighthouse (firefox, webkit)")
    def test_user_flow_non_chromium(self, page, get_film_url, device, throttling, geo, browser_type, pay_method, request):
        self.run_user_flow(page, get_film_url, device, throttling, geo, browser_type, pay_method, request)
        

    @pytest.mark.single_run
    @pytest.mark.domain_goodmovie
    @pytest.mark.browser_chromium
    @allure.story("User Flow: Главная → Фильм → Плеер → Попап → Оплата")
    @allure.title("Полный user flow с Lighthouse (chromium), одиночный прогон")
    def test_user_flow_chromium_single(self, page, get_film_url, device, throttling, geo, browser_type, pay_method, request):
        def main_page_step(page, request, report):
            dns_metrics = metrics.collect_network_metrics(page)
            self._goto_main_page(page, request, report)
            lh_data = self._collect_lighthouse_metrics(self.BASE_URL, request, report)
            report["steps"]["main_page"] = {
                **lh_data,
                "dnsResolveTime": dns_metrics["dnsResolveTime"],
                "connectTime": dns_metrics["connectTime"]
            }
            if lh_data["is_problematic_page"]:
                report["is_problematic_flow"] = True

        def film_page_step(page, request, report):
            dns_metrics = metrics.collect_network_metrics(page)
            lh_data = self._collect_lighthouse_metrics(get_film_url, request, report)
            report["steps"]["film_page"].update({
                **lh_data,
                "dnsResolveTime": dns_metrics["dnsResolveTime"],
                "connectTime": dns_metrics["connectTime"]
            })
            if lh_data["is_problematic_page"]:
                report["is_problematic_flow"] = True

        self.run_user_flow(
            page, get_film_url, device, throttling, geo, browser_type, pay_method, request,
            extra_steps={
                "main_page": main_page_step,
                "film_page_before_video": film_page_step
            }
        )
        
    @pytest.mark.single_run
    @pytest.mark.domain_goodmovie
    @pytest.mark.browser_firefox
    @pytest.mark.browser_webkit
    @allure.story("User Flow: Главная → Фильм → Плеер → Попап → Оплата")
    @allure.title("User flow без Lighthouse (firefox, webkit), одиночный прогон")
    def test_user_flow_non_chromium_single(self, page, get_film_url, device, throttling, geo, browser_type, pay_method, request):
        self.run_user_flow(page, get_film_url, device, throttling, geo, browser_type, pay_method, request)