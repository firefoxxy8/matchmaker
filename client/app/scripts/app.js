'use strict';

/**
 * @ngdoc overview
 * @name matchmakerApp
 * @description
 * # matchmakerApp
 *
 * Main module of the application.
 */
angular
    .module('matchmakerApp', [
        'ngAnimate',
        'ngCookies',
        'ngResource',
        'ngRoute',
        'ngSanitize',
        'ngTouch',
        'base64',
        'ui.bootstrap'
    ])

    .run(function ($rootScope, $window) {

        // Matchmaker thresholds
        $rootScope.minSimilarity = localStorage.getItem("minSimilarity") || 90;
        $rootScope.minMatchSize = localStorage.getItem("minMatchSize") || 20;
        $rootScope.debug = localStorage.getItem("debug") || 'false';

        // API host and credentials
        console.log($window.location.hostname);
        $rootScope.apiHost = $window.location.hostname == 'localhost' ? 'labs.jstor.org.local' : 'labs.jstor.org';
        $rootScope.apiUser = 'demo';
        $rootScope.apiPassword = 'demo';

        $rootScope.apiBaseURL = 'http://' + $rootScope.apiHost + '/api';
        $rootScope.apiToken = null;  // This is loaded on initial request

        $rootScope.tempApiToken = 'af6d34103eed942eaa1cce4f77fd1031af514b65';

    })

    .config(function ($routeProvider) {
        $routeProvider
            .when('/', {
                templateUrl: 'views/matchmaker/index.html',
                controller: 'MatchmakerIndexCtrl',
                controllerAs: 'matchmaker'
            })
            .when('/:work/:version?', {
                templateUrl: 'views/matchmaker/work.html',
                controller: 'MatchmakerWorkCtrl',
                controllerAs: 'matchmaker'
            })
            .when('/about', {
                templateUrl: 'views/about.html',
                controller: 'AboutCtrl',
                controllerAs: 'about'
            })
            .otherwise({
                redirectTo: '/'
            })

        })

    .directive('navMenu', function ($location) {
        return function (scope, element, attrs) {
            var links = element.find('a'),
                currentLink,
                urlMap = {},
                activeClass = attrs.navMenu || 'active';

            for (var i = links.length - 1; i >= 0; i--) {
                var link = angular.element(links[i]);
                var url = link.attr('href');
                if (url.substring(0, 1) === '#') {
                    urlMap[url.substring(1)] = link;
                } else {
                    urlMap[url] = link;
                }
            }

            scope.$on('$routeChangeStart', function () {
                var path = urlMap[$location.path()];
                links.parent('li').removeClass(activeClass);
                if (path) {
                    path.parent('li').addClass(activeClass);
                }
            });
        };
    })

    .directive('resize', function ($window) {
            return function (scope, element) {
                var w = angular.element($window);
                scope.getWindowDimensions = function () {
                    return {
                        'h': w.height(),
                        'w': w.width()
                    };
                };
                scope.$watch(scope.getWindowDimensions, function (newValue, oldValue) {
                    scope.windowHeight = newValue.h;
                    scope.windowWidth = newValue.w;
                    scope.contentHeight = scope.windowHeight - document.querySelector(".modal").offsetTop - 80;
                    scope.contentWidth = document.querySelector(".modal").offsetWidth;
                    console.log('resize',
                        scope.windowHeight,
                        scope.windowWidth,
                        scope.contentHeight,
                        scope.contentWidth,
                        document.querySelector(".modal").offsetHeight,
                        document.querySelector(".modal").offsetWidth,
                        document.querySelector(".modal").offsetTop);
                    scope.style = function () {
                        return {
                            'height': (newValue.h - 100) + 'px',
                            'width': (newValue.w - 100) + 'px'
                        };
                    };

                }, true);

                w.bind('resize', function () {
                    scope.$apply();
                });
            }
        })

    .filter('titlecase', function () {
        return function (input) {
            var smallWords = /^(a|an|and|as|at|but|by|en|for|if|in|nor|of|on|or|per|the|to|vs?\.?|via)$/i;

            input = input.toLowerCase();
            return input.replace(/[A-Za-z0-9\u00C0-\u00FF]+[^\s-]*/g, function (match, index, title) {
                if (index > 0 && index + match.length !== title.length &&
                    match.search(smallWords) > -1 && title.charAt(index - 2) !== ":" &&
                    (title.charAt(index + match.length) !== '-' || title.charAt(index - 1) === '-') &&
                    title.charAt(index - 1).search(/[^\s-]/) < 0) {
                    return match.toLowerCase();
                }

                if (match.substr(1).search(/[A-Z]|\../) > -1) {
                    return match;
                }

                return match.charAt(0).toUpperCase() + match.substr(1);
            });
        }
    })

;
