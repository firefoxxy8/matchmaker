'use strict';

if (!String.prototype.startsWith) {
  String.prototype.startsWith = function(searchString, position) {
    position = position || 0;
    return this.indexOf(searchString, position) === position;
  };
}

/**
 * @ngdoc function
 * @name matchmakerApp.controller:MatchmakerCtrl
 * @description
 * # MatchmakerCtrl
 * Controller of the matchmakerApp
 */
angular.module('matchmakerApp')

    .controller('MatchmakerIndexCtrl', function ($rootScope, $scope, $location, MatchmakerIndex) {

        MatchmakerIndex.getIndex().then(function(indexData){
            $rootScope.works = indexData.works;
            console.log($rootScope.works);
        });

        $scope.loadWork = function(work) {
            var workID = work.id;
            var versionID = work.versions[0].id;
            for (var i = 0; i < work.versions.length; i++) {
                if (work.versions[i].default) {
                    versionID = work.versions[i].id;
                    break;
                }
            }
            console.log('loadWork', workID, versionID);
            var path = '/'+workID+'/'+versionID;
            $location.path(path);
        }

    })

    .controller('MatchmakerWorkCtrl', function ($routeParams, $q, $scope, $rootScope, $window, MatchmakerText, QuoteCountsAPI, MatchDataSOLR, MatchmakerIndex, JWTToken, $uibModal, $log) {
        this.awesomeThings = [
            'HTML5 Boilerplate',
            'AngularJS',
            'Karma'
        ];

        $scope.root = {};
        $scope.articles = [];
        $scope.selectedChunk = '';

        $scope.getWorkTextAndCounts = function(workID, workURL) {
            $q.all([
                QuoteCountsAPI.getCounts(workID),
                MatchmakerText.getText(workURL)
            ]).then(function (values) {
                var quoteCounts = values[0];
                //console.log(quoteCounts);
                var workText = values[1];
                //console.log(workText);

                marked(workText, { renderer: renderer });

                $scope.root = {id: 'root', children: []};

                var renderer = new marked.Renderer();

                renderer.heading = function (text, level) {

                    var parent = $scope.root;
                    for (var l = 0; l < level-1; l++) {
                        parent = parent.children.slice(-1)[0];
                    }

                    //console.log('heading','h'+level,text);
                    var new_node = {
                        type: 'group',
                        id: null,
                        label: text,
                        parent: parent,
                        children: [],
                        num_quotes: 0
                    };
                    parent.children.push(new_node);
                };

                renderer.paragraph = function (text) {
                    console.log('paragraph',text);
                };

                renderer.html = function (text) {
                    var parent = $scope.root;
                    while (parent.children && parent.children.length > 0) {
                        var last = parent.children.slice(-1)[0];
                        if (last.children) {
                            parent = last;
                        } else {
                            break;
                        }
                    }

                    var el = document.createElement( 'div' );
                    el.innerHTML = text;
                    var paragraphs = el.getElementsByTagName('p');
                    if (paragraphs.length == 1) {
                        var para_id = paragraphs[0].id;
                        var para_text = paragraphs[0].innerHTML;
                        //console.log('html paragraph',chunk_id,chunk_text);
                        var para = {
                            type: 'para',
                            id: para_id,
                            parent: parent,
                            num_quotes: quoteCounts[para_id],
                            text: para_text
                        };
                        parent.children.push(para);

                        var id_parts = para_id.split('-');
                        var parent_node = $scope.root;
                        for (var p = 1; p < id_parts.length; p++) {
                            var parent_node = parent_node.children[parent_node.children.length - 1];
                            var chunk_Id = id_parts.slice(0, p).join('-');
                            parent_node.id = chunk_Id;
                            parent_node.num_quotes = quoteCounts[chunk_Id];
                        }
                    }
                };

                marked(workText, { renderer: renderer });

                console.log($scope.root);
            });
        }

        console.log($routeParams);
        $scope.workID = null;
        $scope.versionID = null;;
        $scope.url;

        if ($routeParams.work) {$scope.workID = $routeParams.work;}
        if ($routeParams.version) {$scope.versionID = $routeParams.version;}

        MatchmakerIndex.getIndex().then(function(indexData){
            var workURL;
            var works = indexData;
            var work = works[$scope.workID];
            if ($scope.versionID) {
                workURL = work.versions[$scope.versionID];
            } else {
                for (var versionID in work.versions) {
                    workURL = work.versions[versionID].url;
                    if (work.versions[versionID].default == true) break
                }
            }
            $scope.getWorkTextAndCounts($scope.workID, workURL);
        });

        console.log('work='+$scope.workID+' version='+$scope.versionID+' url='+$scope.url);

        $scope.log = function(s) {
            console.log(s);
        }

        $scope.getBootstrapSize = function () {
            //set a $scope variable or a service variable that reused
            if ($window.innerWidth >= 1200) {
                return 'lg';
            } else if ($window.innerWidth >= 992) {
                return 'md';
            } else if ($window.innerWidth >= 768) {
                return 'sm';
            } else {
                return 'xs'
            }
        };

        $scope.showArticles = function(chunkid) {
            console.log('showArticles', chunkid);
            MatchDataSOLR.getMatches($scope.workID, chunkid).then(
                function (response) {
                    $scope.articles = aggregateMatchData(response.docs);
                    var size = $scope.getBootstrapSize();
                    console.log(size);
                    if (size == 'xs' || size == 'sm') {
                        $scope.openMatchesModal('lg');
                    }
                }
            );
        }

        $scope._open = [];
        $scope.isShown = function (node) {
            var isShown =  node.parent.id == 'root' || $scope.isOpen(node.parent);
            //if (isShown) console.log('isShown',node.id,isShown);
            return isShown;
        };
        $scope.isOpen = function(node) {
            var isOpen = $scope._open.indexOf(node.id) >= 0;
            //console.log('isOpen',node.id,isOpen);
            return isOpen;
        };

        $scope.toggle = function (node) {
            var idx = $scope._open.indexOf(node.id);
            if (idx >= 0) {
                $scope._open = $scope._open.slice(0,idx);
                console.log('toggle','close',node.id,$scope._open);
            } else {
                $scope._open = [node.id];
                var cur = node;
                while (cur.parent) {
                    cur = cur.parent;
                    $scope._open.unshift(cur.id);
                }
                console.log('toggle','open',node.id,$scope._open);
            }
        };

        $scope.openMatchesModal = function (size) {

            var modalInstance = $uibModal.open({
                animation: false,
                templateUrl: 'views/matchmaker/matches_modal.html',
                controller: 'ModalInstanceCtrl',
                size: size,
                resolve: {
                    articles: function () {
                        return $scope.articles;
                    },
                    selectedChunk: function () {
                        return $scope.selectedChunk;
                    }
                }
            });
            modalInstance.result.then(function (selectedItem) {
                $scope.selected = selectedItem;
            }, function () {
                $log.info('Modal dismissed at: ' + new Date());
            });
        };

        $scope.articleViewerModal = function(matchID){
            var bootstrapSize = $scope.getBootstrapSize();
            console.log('articleViewerModal',matchID,bootstrapSize);
            var articleViewerModalInstance = $uibModal.open({
                animation: false,
                //size: bootstrapSize,
				templateUrl : 'views/matchmaker/article_viewer_modal.html',
				controller : 'ArticleViewerModalCtrl',
                resolve: {
                    matchID: function () {
                        return matchID;
                    }
                }
			});

			articleViewerModalInstance.result.then(function(data) {
		        $scope.name = data;
			});
        };
    })

    .controller('ModalInstanceCtrl', function ($scope, $uibModal, $uibModalInstance, articles, selectedChunk) {
        $scope.articles = articles;
        $scope.selectedChunk = selectedChunk.split('-');
        $scope.selected = {
            item: $scope.articles[0]
        };

        $scope.ok = function () {
            $uibModalInstance.close($scope.selected.item);
        };

        $scope.cancel = function () {
            $uibModalInstance.dismiss('cancel');
        };

        $scope.matchSelected = function(matchID) {
            console.log('matchSelected', matchID);
        };

        $scope.articleViewerModal = function(matchID){
            var articleViewerModalInstance = $uibModal.open({
                animation: false,
                size: 'lg',
				templateUrl : 'views/matchmaker/article_viewer_modal.html',
				controller : 'ArticleViewerModalCtrl',
                resolve: {
                    matchID: function () {
                        return matchID;
                    }
                }
			});

			articleViewerModalInstance.result.then(function(data) {
		        $scope.name = data;
			});
        };
    })

    .controller('ArticleViewerModalCtrl', function ($scope, $rootScope, $uibModalInstance, ImageMetadata, $window, matchID) {
        $scope.matchID = matchID;

        $scope.allImages = [];

        var split = matchID.split('|');
        $scope.pageNum = parseInt(split[2]);
        var articleid = split.slice(0, 2).join('/');
        $scope.image = null;
        ImageMetadata.getImageMetadata(articleid).then(function (results) {
            var modalWidth = document.querySelector(".modal-content").offsetWidth;
            var scaledWidth = modalWidth*0.9;
            for (var pageSeq = 0; pageSeq < results.data.length; pageSeq++) {
                var scaledHeight = scaledWidth/results.data[pageSeq].width * results.data[pageSeq].height;
                var imageData = {
                    url: 'http://' + $rootScope.apiHost + results.data[pageSeq].url + '?token=' + $rootScope.tempApiToken,
                    type: results.data[pageSeq].type,
                    imageWidth: results.data[pageSeq].width,
                    imageHeight: results.data[pageSeq].height,
                    scaledHeight: scaledHeight,
                    scaledWidth: scaledWidth,
                    label: results.data[pageSeq].label,
                    seq: pageSeq
                }
                $scope.allImages.push(imageData);
            }
            $scope.image = $scope.allImages[$scope.pageNum-1];
        });

        $scope.ok = function () {
            $uibModalInstance.close($scope.selected.item);
        };

        $scope.cancel = function () {
            $uibModalInstance.dismiss('cancel');
        };

    })

    .service('JWTToken', function ($http, $q, $rootScope) {
        var cachedToken, p;
        return {
            getToken: function(refresh) {
                console.log('getToken',refresh);
                return $q.when(refresh ? helper() : cachedToken || p || helper());
            }
        }
        function helper () {
            var deferred = $q.defer();
            p = deferred.promise;
            $http({
                method: 'POST', url: $rootScope.apiBaseURL + '/token-auth/',
                headers: {'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8'},
                data: $.param({username: $rootScope.apiUser, password: $rootScope.apiPassword})
            }).success(function (data) {
                cachedToken = data.token;
                deferred.resolve(data.token);
            }).error(function (data) {
                deferred.reject('Error')
            })
            return deferred.promise;
        }

    })

    .service("QuoteCountsAPI", function ($rootScope, $http, JWTToken, $q) {
        return {
            getCounts: function (work) {
                return JWTToken.getToken().then(function (token) {
                    return helper(work, token);
                });
            }
        }
        function helper(work, token, d) {
            var deferred = d || $q.defer();
            var url = $rootScope.apiBaseURL + '/matchmaker/?work=' + work +
                '&similarity=[' + $rootScope.minSimilarity / 100 + '+TO+*]' +
                '&match_size=[' + $rootScope.minMatchSize + '+TO+*]' +
                '&facet=chunk_ids.10000,docid[unique]';

            $http.get(url, {headers: {'Authorization': 'JWT ' + token}}).then(
                function (response) {
                    var quoteCounts = {};
                    for (var i = 0; i < response.data.facets.chunk_ids.values.length; i++) {
                        var facet = response.data.facets.chunk_ids.values[i];
                        var chunk_id = facet.val;
                        var count = facet.docid.stats.unique;
                        quoteCounts[chunk_id] = count;
                    }
                    deferred.resolve(quoteCounts);
                },
                function(err) {
                    if (!d) {
                        JWTToken.getToken(true).then(
                            function (token) {
                                return helper(work, token, deferred);
                            },
                            function (err) {
                                deferred.reject(err);
                            });
                    } else {
                        deferred.reject(err);
                    }
                });
            return deferred.promise;

        }
    })

    .service('MatchmakerIndex', function ($http, $q) {
        var index, p;
        return {
            getIndex: function(refresh) {
                console.log('getIndex',refresh);
                return $q.when(refresh ? helper() : index || p || helper());
            }
        }
        function helper () {
            var deferred = $q.defer();
            p = deferred.promise;
            var url = 'https://raw.githubusercontent.com/JSTOR-Labs/matchmaker/master/works/index.json';
            $http.get(url).then(
                function(response) {
                    index = response.data;
                    deferred.resolve(response.data);
                },
                function(err) {
                    deferred.reject(err);
                }
            );
            return deferred.promise;
        }

    })

    .service('MatchmakerText', function ($http, $q) {
        return {
            getText: function (url) {
                var deferred = $q.defer();
                $http.get(url).then(
                    function (response) {
                        deferred.resolve(response.data);
                    }
                );
                return deferred.promise;
            }
        }
    })

    .service("MatchDataSOLR", function ($rootScope, $http, JWTToken, $q) {
        return {
            getMatches: function (work, chunkID) {
                return JWTToken.getToken().then(function(token) {
                    return helper(work, chunkID, token);
                });
            }
        };
        function helper(work, chunkID, token, d) {
            var deferred = d || $q.defer();
            var url = $rootScope.apiBaseURL + '/solr/matchmaker/select/?fq=work:' + work + '&wt=json' +
                '&fq=similarity:[' + $rootScope.minSimilarity / 100 + '+TO+*]&fq=match_size:[' + $rootScope.minMatchSize + '+TO+*]' +
                '&fl=score,*&rows=100&fq=chunk_ids:' + chunkID;
            url += '&bf=product(similarity,250)';
            url += '&bf=div(match_size,10)';
            $http.get(url, {headers: {'Authorization': 'JWT ' + token}}).then(
                function (response) {
                    deferred.resolve({'docs': response.data.response.docs});
                },
                function (err) {
                    if (!d) {
                        JWTToken.getToken(true).then(
                            function (token) {
                                return helper(work, chunkID, token, deferred);
                            },
                            function (err) {
                                deferred.reject(err);
                            });
                    } else {
                        deferred.reject(err);
                    }
                });
            return deferred.promise;
        }
    })

    .service("ImageMetadata", function ($rootScope, $http) {
        return {
            getImageMetadata: function (articleid) {
                var url = 'http://' + $rootScope.apiHost + '/demo/images/' + articleid;
                return $http.get(url, {headers: {'Authorization': 'Token ' + $rootScope.tempApiToken}});
            }
        };
    })

;